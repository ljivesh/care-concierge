"""The HTTP endpoints, through the real FastAPI app, graph, checkpointer and database.

Model calls are scripted fakes. Holds the chat-level version of the required
duplicate-request test, and the "process died before the reply" case.
"""

import asyncio
import json
import uuid

import httpx
import pytest
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy import func, select

from app import main, replies, safety
from app.contract import Intent, SafetyVerdict
from app.db.models import Escalation, ServiceRequest
from app.graph import respond, router, verify
from app.graph.router import Route
from app.main import app
from app.replies import Language
from app.safety import SafetyDecision


@pytest.fixture
async def client(session_factory, embedder, monkeypatch):  # session_factory empties the write tables first
    monkeypatch.setattr(main, "Embedder", lambda: embedder)  # reuse the loaded model; loading takes seconds
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


def script(monkeypatch, *, verdict=SafetyVerdict.SAFE, intents=(Intent.BOOK_SERVICE,), reply=None):
    async def fake_safety(llm, message):
        return SafetyDecision(verdict=verdict, language=Language.EN)

    async def fake_router(llm, conversation):
        return Route(intents=list(intents))

    monkeypatch.setattr(safety, "ask_model", fake_safety)
    monkeypatch.setattr(router, "ask_model", fake_router)
    monkeypatch.setattr(respond, "ask_model", reply)

    async def fake_check(llm, question, passages, answer):
        return verify.Grounding(supported=True, reason="scripted")

    monkeypatch.setattr(verify, "ask_model", fake_check)


async def books_cardiology(llm, tools, messages):
    """Reply-model stand-in: book once, then report the booking id it was given."""
    if isinstance(messages[-1], ToolMessage):
        result = messages[-1].artifact
        return AIMessage(result["error"]["message"] if "error" in result else f"Booked: {result['id']}")
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "book_service",
                "args": {"service": "DOCTOR", "subtype": "CARDIOLOGY", "scheduled_for": "2027-01-12T10:30"},
                "id": f"call-{uuid.uuid4().hex[:8]}",
                "type": "tool_call",
            }
        ],
    )


def chat_body(**overrides) -> dict:
    return {
        "thread_id": str(uuid.uuid4()),
        "patient_id": "pat_001",
        "message": "book cardiology on 12 Jan 2027 at 10:30",
        "request_id": str(uuid.uuid4()),
        **overrides,
    }


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def chat(client, body: dict) -> list[tuple[str, dict]]:
    response = await client.post("/v1/chat", json=body)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


def final(events) -> dict:
    assert events[-1][0] == "final", events
    return events[-1][1]


async def booking_count(session_factory) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(ServiceRequest))


# ---------- basics ----------


async def test_healthz(client):
    response = await client.get("/healthz")

    assert response.status_code == 200 and response.json() == {"status": "ok"}


async def test_page_is_served(client):
    response = await client.get("/")

    assert response.status_code == 200 and "Care Concierge" in response.text


async def test_chat_streams_tool_events_then_the_reply(client, session_factory, monkeypatch):
    script(monkeypatch, reply=books_cardiology)

    events = await chat(client, chat_body())

    assert [name for name, _ in events] == ["tool_call", "tool_result", "token", "final"]
    call, result = events[0][1], events[1][1]
    assert call["name"] == "book_service" and "patient_id" not in call["args"]
    assert result["status"] == "success" and result["result"]["clinician_name"] == "Dr. Arvind Khanna"
    assert final(events)["reply"] == f"Booked: {result['result']['id']}"
    assert final(events)["intents"] == ["BOOK_SERVICE"] and final(events)["safety_verdict"] == "SAFE"
    assert await booking_count(session_factory) == 1


# ---------- required test 2: the same chat request sent twice ----------


async def test_same_request_twice_one_booking_and_both_replies_report_it(client, session_factory, monkeypatch):
    script(monkeypatch, reply=books_cardiology)
    body = chat_body()

    first = await chat(client, body)
    second = await chat(client, body)

    assert await booking_count(session_factory) == 1
    async with session_factory() as session:
        booking_id = str(await session.scalar(select(ServiceRequest.id)))
    assert final(first)["reply"] == final(second)["reply"] == f"Booked: {booking_id}"
    assert final(first)["replayed"] is False and final(second)["replayed"] is True


async def test_same_request_twice_at_the_same_moment(client, session_factory, monkeypatch):
    script(monkeypatch, reply=books_cardiology)
    body = chat_body()

    first, second = await asyncio.gather(chat(client, body), chat(client, body))

    assert await booking_count(session_factory) == 1
    assert final(first)["reply"] == final(second)["reply"]
    assert final(first)["reply"].startswith("Booked: ")


async def test_booking_written_then_process_dies_then_patient_resends(client, session_factory, monkeypatch):
    """The 'one short answer' scenario: the row exists, the reply was never sent."""
    died = False

    async def dies_before_replying(llm, tools, messages):
        nonlocal died
        if isinstance(messages[-1], ToolMessage) and not died:
            died = True
            raise asyncio.CancelledError()  # the process stops here, after the booking was written
        return await books_cardiology(llm, tools, messages)

    script(monkeypatch, reply=dies_before_replying)
    body = chat_body()

    interrupted = await chat(client, body)
    assert "final" not in [name for name, _ in interrupted]  # the patient never got a reply
    assert await booking_count(session_factory) == 1  # but the booking was written

    events = await chat(client, body)  # the patient sends the same message again

    assert await booking_count(session_factory) == 1  # no second booking
    async with session_factory() as session:
        booking_id = str(await session.scalar(select(ServiceRequest.id)))
    assert final(events)["reply"] == f"Booked: {booking_id}"  # and they are told about the first one
    assert "tool_call" not in [name for name, _ in events]  # resumed after the tool; it did not run again


async def test_two_patients_same_slot_one_booking_one_clear_message(client, session_factory, monkeypatch):
    script(monkeypatch, reply=books_cardiology)

    first, second = await asyncio.gather(
        chat(client, chat_body(patient_id="pat_001")), chat(client, chat_body(patient_id="pat_002"))
    )

    replies_sent = sorted([final(first)["reply"], final(second)["reply"]])
    assert await booking_count(session_factory) == 1
    assert replies_sent[0].startswith("Booked: ")
    assert "has just been taken" in replies_sent[1] and "constraint" not in replies_sent[1]


# ---------- safety through the API ----------


async def test_emergency_stream(client, session_factory, monkeypatch):
    script(monkeypatch, verdict=SafetyVerdict.EMERGENCY, reply=None)

    events = await chat(client, chat_body(patient_id="pat_016", message="my father just collapsed"))

    assert [name for name, _ in events] == ["tool_call", "tool_result", "token", "final"]
    assert events[0][1]["name"] == "escalate_emergency"
    assert final(events)["reply"] == replies.emergency(
        Language.EN, hospital="Sanjeevani Hospital", phone="+91 124 4000 1100", minutes=5
    )
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Escalation)) == 1


async def test_classifier_down_patient_sees_the_fixed_reply_and_no_tool_event(client, session_factory, monkeypatch):
    async def provider_down(llm, message):
        raise ConnectionError("provider down")

    monkeypatch.setattr(safety, "ask_model", provider_down)

    events = await chat(client, chat_body())

    assert [name for name, _ in events] == ["token", "final"]
    assert final(events)["reply"] == replies.safety_unavailable(Language.HINGLISH)  # pat_001's language
    assert final(events)["safety_verdict"] is None
    assert await booking_count(session_factory) == 0


# ---------- requests we refuse ----------


async def test_unknown_patient_is_404(client):
    response = await client.post("/v1/chat", json=chat_body(patient_id="pat_999"))

    assert response.status_code == 404


async def test_request_id_must_be_a_uuid(client):
    response = await client.post("/v1/chat", json=chat_body(request_id="not-a-uuid"))

    assert response.status_code == 422


async def test_a_thread_cannot_be_used_by_another_patient(client, monkeypatch):
    script(monkeypatch, reply=books_cardiology)
    body = chat_body()
    await chat(client, body)

    response = await client.post("/v1/chat", json=chat_body(thread_id=body["thread_id"], patient_id="pat_010"))

    assert response.status_code == 403


# ---------- transcript ----------


async def test_transcript_comes_from_the_checkpointer(client, monkeypatch):
    script(monkeypatch, reply=books_cardiology)
    body = chat_body()
    events = await chat(client, body)

    response = await client.get(f"/v1/threads/{body['thread_id']}")

    data = response.json()
    assert response.status_code == 200 and data["patient_id"] == "pat_001"
    assert [m["role"] for m in data["messages"]] == ["user", "tool_call", "tool_result", "assistant"]
    assert data["messages"][0]["content"] == body["message"]
    assert data["messages"][-1]["content"] == final(events)["reply"]


async def test_unknown_thread_is_404(client):
    assert (await client.get(f"/v1/threads/{uuid.uuid4()}")).status_code == 404
