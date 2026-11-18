"""The HTTP surface: three endpoints from the contract, plus the page."""

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field

from app import scoping
from app.chat import ThreadLocks, stream_turn
from app.checkpoint import open_checkpointer
from app.config import get_settings
from app.db.models import Society
from app.db.session import make_engine, make_session_factory
from app.embeddings import Embedder
from app.graph.build import build_graph
from app.graph.nodes import Deps
from app.graph.state import new_turn
from app.llm import make_llm
from app.replies import Language
from app.tools import make_tools

FRONTEND_DIR = Path(get_settings().frontend_dir)  # the built React app (frontend/ in the repo)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build everything once at startup and keep it on app.state. No globals."""
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    tools = make_tools(session_factory, Embedder(), min_similarity=settings.retrieval_min_similarity)
    async with open_checkpointer(settings) as checkpointer:
        app.state.session_factory = session_factory
        app.state.graph = build_graph(Deps(llm=make_llm(settings), tools=tools, settings=settings), checkpointer)
        app.state.thread_locks = ThreadLocks()
        yield
    await engine.dispose()


app = FastAPI(title="Care Concierge", lifespan=lifespan)
# Vite puts the hashed JS and CSS bundles under /assets.
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets", check_dir=False), name="assets")


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=200)
    patient_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)
    request_id: uuid.UUID
    language: Language | None = None


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def page() -> FileResponse:
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        raise HTTPException(503, "The frontend has not been built. Run `docker compose up --build`.")
    return FileResponse(index)


@app.post("/v1/chat")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    graph = request.app.state.graph
    async with request.app.state.session_factory() as session:
        patient = await scoping.get_patient(session, body.patient_id)
        if patient is None:
            raise HTTPException(404, "We could not find that patient.")
        society = await session.get(Society, patient.society_id)

    config = {"configurable": {"thread_id": body.thread_id}}
    owner = (await graph.aget_state(config)).values.get("patient_id")
    if owner not in (None, patient.id):
        raise HTTPException(403, "This conversation belongs to another patient.")

    turn_input = new_turn(
        message=body.message,
        patient_id=patient.id,
        # The society comes from the patient's row. Nothing in the request can change it.
        society_id=patient.society_id,
        timezone=society.timezone,
        request_id=str(body.request_id),
        # A hint only; the safety node replaces it with the language of the message.
        language=(body.language.value if body.language else patient.language),
    )

    async def events():
        async with request.app.state.thread_locks.for_thread(body.thread_id):
            async for event in stream_turn(
                graph, thread_id=body.thread_id, request_id=str(body.request_id), turn_input=turn_input
            ):
                yield event

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/v1/threads/{thread_id}")
async def transcript(thread_id: str, request: Request) -> dict:
    """The conversation so far, read from the LangGraph checkpointer."""
    state = (await request.app.state.graph.aget_state({"configurable": {"thread_id": thread_id}})).values
    if not state:
        raise HTTPException(404, "No conversation with that id.")

    messages = []
    for m in state["messages"]:
        if isinstance(m, HumanMessage):
            messages.append({"role": "user", "content": m.content})
        elif isinstance(m, ToolMessage):
            messages.append({"role": "tool_result", "id": m.tool_call_id, "name": m.name, "status": m.status, "result": m.artifact})
        elif isinstance(m, AIMessage):
            for call in m.tool_calls:
                messages.append({"role": "tool_call", "id": call["id"], "name": call["name"], "args": call["args"]})
            if m.content:
                messages.append({"role": "assistant", "content": m.content})
    return {
        "thread_id": thread_id,
        "patient_id": state["patient_id"],
        "messages": messages,
        # Citations of the most recent reply.
        "citations": state["citations"],
    }
