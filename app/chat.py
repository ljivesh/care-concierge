"""One chat turn as a stream of Server-Sent Events.

Events, in the order a client can expect them:
    tool_call    the graph is about to run a tool            {id, name, args}
    tool_result  what the tool returned                      {id, name, status, result}
    token        a piece of the reply text                   {text}
    citation     a document section the reply cites          {n, doc_id, title, heading_path}
    final        the turn is complete                        {reply, safety_verdict, intents, ...}
    error        the turn failed                             {message}

The same request sent twice (same thread, same request_id):
  - if the first run finished, nothing runs again: the stored turn is replayed;
  - if the first run died part-way, the graph resumes from its last checkpoint.
"""

import asyncio
import json
import logging
import weakref
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from app.contract import Intent
from app.graph.respond import NO_ANSWER
from app.graph.state import this_turn

log = logging.getLogger("concierge.chat")

FIXED_REPLY_NODES = {"escalate", "fixed_reply"}  # their text is not streamed by a model


class ThreadLocks:
    """One turn at a time per thread, so a duplicate request waits for the first
    to finish and then replays it. Locks vanish when nobody holds them."""

    def __init__(self) -> None:
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    def for_thread(self, thread_id: str) -> asyncio.Lock:
        lock = self._locks.get(thread_id)
        if lock is None:
            lock = self._locks[thread_id] = asyncio.Lock()
        return lock


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _tool_events(message: AnyMessage) -> list[str]:
    if isinstance(message, AIMessage):
        return [sse("tool_call", {"id": c["id"], "name": c["name"], "args": c["args"]}) for c in message.tool_calls]
    if isinstance(message, ToolMessage):
        return [
            sse(
                "tool_result",
                {"id": message.tool_call_id, "name": message.name, "status": message.status, "result": message.artifact},
            )
        ]
    return []


async def stream_turn(
    graph: CompiledStateGraph, *, thread_id: str, request_id: str, turn_input: dict
) -> AsyncIterator[str]:
    config = {"configurable": {"thread_id": thread_id}}
    streamed = ""  # reply text already sent as tokens
    held = ""  # text held back while it could still turn out to be the NO_ANSWER marker
    try:
        before = await graph.aget_state(config)
        seen_before = before.values.get("request_id") == request_id
        replayed = seen_before and not before.next

        # A clinic answer is checked against its passages before it is shown (the verify
        # node), so its tokens are held back and the checked reply is sent in one piece.
        hold_reply = seen_before and before.values.get("intents") == [Intent.CLINIC_INFO.value]

        if replayed:
            # This request already ran to the end. Report it again; run nothing.
            for message in this_turn(before.values["messages"])[1:]:
                for event in _tool_events(message):
                    yield event
        else:
            # None = continue from the last checkpoint (the earlier run died part-way).
            graph_input = None if seen_before else turn_input
            async for mode, chunk in graph.astream(graph_input, config, stream_mode=["messages", "updates"]):
                if mode == "messages":
                    piece, meta = chunk
                    # Only the reply-writing model's text; the safety and router calls stay private.
                    if hold_reply:
                        continue
                    if meta.get("langgraph_node") == "respond" and isinstance(piece, AIMessageChunk) and isinstance(piece.content, str) and piece.content:
                        held += piece.content
                        if not streamed:
                            held = held.lstrip()  # models often open with blank lines
                        if held and not NO_ANSWER.startswith(held.strip()):
                            streamed += held
                            yield sse("token", {"text": held})
                            held = ""
                else:
                    for node, update in chunk.items():
                        if node == "router" and update:
                            hold_reply = update.get("intents") == [Intent.CLINIC_INFO.value]
                        for message in (update or {}).get("messages", []):
                            for event in _tool_events(message):
                                streamed = held = ""  # text before a tool call was not the reply
                                yield event
                            if node in FIXED_REPLY_NODES and isinstance(message, AIMessage) and message.content:
                                streamed += message.content
                                yield sse("token", {"text": message.content})

        state = (await graph.aget_state(config)).values
        reply = str(state["messages"][-1].content)
        if streamed.strip() != reply:
            # Nothing (or something else) was streamed: send the reply in one piece.
            yield sse("token", {"text": reply, "replace": True})
        for citation in state["citations"]:
            yield sse("citation", citation)
        yield sse(
            "final",
            {
                "thread_id": thread_id,
                "request_id": request_id,
                "reply": reply,
                "language": state["language"],
                "safety_verdict": state["safety_verdict"],
                "intents": state["intents"],
                "citations": state["citations"],
                "replayed": replayed,
            },
        )
    except Exception:
        log.exception("chat_turn_failed thread_id=%s request_id=%s", thread_id, request_id)
        yield sse("error", {"message": "Something went wrong on our side. Please send your message again."})
