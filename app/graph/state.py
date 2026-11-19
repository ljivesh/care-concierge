"""The graph's state: what every node reads and what it may update.

LangGraph saves this whole dictionary to Postgres (the checkpointer) after
every step, keyed by thread_id. `messages` is the transcript and survives
across turns; the other per-turn fields are reset by `new_turn`.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.graph.message import add_messages


class ConciergeState(TypedDict):
    # The transcript. `add_messages` appends what a node returns instead of
    # replacing the list; a message with an id already present replaces that one.
    messages: Annotated[list[AnyMessage], add_messages]
    # Who is talking. Set by the server from the patient's row, never by the model.
    patient_id: str
    society_id: str
    timezone: str
    # The client's id for this message; makes writes idempotent.
    request_id: str
    # en | hi | hinglish. Starts as a hint, then set by the safety node.
    language: str
    # EMERGENCY | MEDICAL_ADVICE | SAFE, or None when the classifier failed.
    safety_verdict: str | None
    # From the router, most important first. Decides which tools may be used.
    intents: list[str]
    # Tool calls made so far in this turn, checked against the cap.
    tool_calls_made: int
    # Passages the final answer cites: {n, doc_id, title, heading_path}.
    citations: list[dict]


def new_turn(
    *, message: str, patient_id: str, society_id: str, timezone: str, request_id: str, language: str
) -> dict:
    """Graph input for one incoming message."""
    return {
        # id = request_id: if the same request is sent again, the message is replaced, not duplicated.
        "messages": [HumanMessage(content=message, id=request_id)],
        "patient_id": patient_id,
        "society_id": society_id,
        "timezone": timezone,
        "request_id": request_id,
        "language": language,
        "safety_verdict": None,
        "intents": [],
        "tool_calls_made": 0,
        "citations": [],
    }


def latest_user_text(state: ConciergeState) -> str:
    return next(m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage))


def previous_assistant_text(state: ConciergeState) -> str | None:
    """What the assistant last said before the patient's latest message, if anything."""
    seen_latest = False
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            if seen_latest:
                return None  # reached the turn before without finding assistant text
            seen_latest = True
        elif seen_latest and isinstance(message, AIMessage) and str(message.content).strip():
            return str(message.content)
    return None


def this_turn(messages: list[AnyMessage]) -> list[AnyMessage]:
    """The latest patient message and everything after it."""
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return messages[index:]
    return []


def passages_this_turn(messages: list[AnyMessage]) -> list[dict]:
    """Numbered passages returned by search during this turn."""
    return [
        passage
        for m in this_turn(messages)
        if isinstance(m, ToolMessage) and m.name == "search_clinic_docs" and m.status == "success"
        for passage in (m.artifact or [])
    ]


def without_dangling_tool_calls(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Model APIs reject a tool call with no result (and a result with no call).

    That can be left behind if the process died between the two, so drop both
    kinds before sending history to the model.
    """
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    kept: list[AnyMessage] = []
    open_calls: set[str] = set()
    for m in messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            if not all(call["id"] in answered for call in m.tool_calls):
                continue
            open_calls |= {call["id"] for call in m.tool_calls}
        elif isinstance(m, ToolMessage) and m.tool_call_id not in open_calls:
            continue
        kept.append(m)
    return kept
