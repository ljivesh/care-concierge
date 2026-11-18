"""The graph end to end, with the three model calls replaced by scripted fakes.

Everything else is real: the LangGraph graph, the Postgres checkpointer, the
tools and the database. Holds the third required test (restart and continue)
and the safety-failure tests (what the patient sees, and that no tool ran).
"""

import asyncio
import re
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import func, select

from app import replies, safety
from app.checkpoint import open_checkpointer
from app.config import get_settings
from app.contract import Intent, SafetyVerdict
from app.db.models import Escalation, ServiceRequest, SymptomLog
from app.graph import nodes, respond, router
from app.graph.build import build_graph
from app.graph.nodes import Deps
from app.graph.router import Route
from app.graph.state import new_turn
from app.replies import Language
from app.safety import SafetyDecision
from app.tools import make_tools

# ---------- helpers ----------


@pytest.fixture
def deps(session_factory, embedder):
    return Deps(
        llm=object(),  # never used: every model call is replaced
        tools=make_tools(session_factory, embedder, min_similarity=get_settings().retrieval_min_similarity),
        settings=get_settings().model_copy(update={"safety_timeout_s": 0.3}),
    )


@pytest.fixture
def tool_runs(monkeypatch):
    """Records every tool that actually runs, whichever node runs it."""
    ran: list[str] = []
    real = nodes.run_tool

    async def recording(tools, name, args, *, timeout_s):
        ran.append(name)
        return await real(tools, name, args, timeout_s=timeout_s)

    monkeypatch.setattr(nodes, "run_tool", recording)
    return ran


def must_not_be_called(what: str):
    async def fail(*args, **kwargs):
        raise AssertionError(f"{what} must not be called")

    return fail


def script(monkeypatch, *, verdict=SafetyVerdict.SAFE, language=Language.EN, intents=None, search_query=None, reply=None):
    """Replace the three model calls. Anything left as None must not be called."""

    async def fake_safety(llm, message):
        return SafetyDecision(verdict=verdict, language=language)

    async def fake_router(llm, conversation):
        return Route(intents=intents, search_query=search_query)

    monkeypatch.setattr(safety, "ask_model", fake_safety)
    monkeypatch.setattr(router, "ask_model", fake_router if intents else must_not_be_called("the router"))
    monkeypatch.setattr(respond, "ask_model", reply or must_not_be_called("the reply model"))


def tool_call(name: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call-{uuid.uuid4().hex[:8]}", "type": "tool_call"}])


async def send(graph, thread_id: str, message: str, *, patient_id="pat_001", society_id="soc_shivalik", language="en", request_id=None):
    return await graph.ainvoke(
        new_turn(
            message=message,
            patient_id=patient_id,
            society_id=society_id,
            timezone="Asia/Kolkata",
            request_id=request_id or str(uuid.uuid4()),
            language=language,
        ),
        {"configurable": {"thread_id": thread_id}},
    )


async def count(session_factory, model) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(model))


def reply_text(state) -> str:
    return state["messages"][-1].content


async def booking_assistant(llm, tools, messages):
    """A stand-in for the reply model that only knows what is in the messages it is given.

    It books cardiology once it can find both the department and a date in the
    conversation; otherwise it asks for what is missing.
    """
    if isinstance(messages[-1], ToolMessage):
        return AIMessage("Could not book." if messages[-1].status == "error" else "Your appointment is booked.")
    said = " ".join(m.content for m in messages if isinstance(m, HumanMessage)).lower()
    when = re.search(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})", said)
    if "cardiology" in said and when:
        return tool_call("book_service", service="DOCTOR", subtype="CARDIOLOGY", scheduled_for=f"{when[1]}T{when[2]}")
    if "cardiology" in said:
        return AIMessage("Which date and time would you like?")
    return AIMessage("Which department would you like to book?")


# ---------- the shape of the graph ----------


def test_no_path_reaches_a_tool_without_passing_safety(deps, checkpointer):
    drawn = build_graph(deps, checkpointer).get_graph()
    edges = [(e.source, e.target) for e in drawn.edges]

    assert [target for source, target in edges if source == "__start__"] == ["safety"]

    # Remove the safety node and see what START can still reach: nothing.
    reachable, frontier = set(), ["__start__"]
    while frontier:
        node = frontier.pop()
        for source, target in edges:
            if source == node and target != "safety" and target not in reachable:
                reachable.add(target)
                frontier.append(target)
    assert reachable == set()


# ---------- the safety classifier fails: what the patient sees, and no tool ran ----------


async def classifier_raises(llm, message):
    raise ConnectionError("provider down")


async def classifier_hangs(llm, message):
    await asyncio.sleep(30)


@pytest.mark.parametrize("broken_classifier", [classifier_raises, classifier_hangs])
@pytest.mark.parametrize(
    "message, language",
    [
        ("book cardiology on 2027-01-12 10:30", "en"),
        ("my father just collapsed and isnt responding", "en"),
        ("रविवार को वेलनेस रूम कितने बजे खुलता है?", "en"),
    ],
)
async def test_classifier_failure_blocks_the_message_and_runs_no_tool(
    deps, checkpointer, session_factory, monkeypatch, tool_runs, broken_classifier, message, language
):
    monkeypatch.setattr(safety, "ask_model", broken_classifier)
    monkeypatch.setattr(router, "ask_model", must_not_be_called("the router"))
    monkeypatch.setattr(respond, "ask_model", must_not_be_called("the reply model"))
    graph = build_graph(deps, checkpointer)

    state = await send(graph, str(uuid.uuid4()), message, language=language)

    expected_language = replies.guess_language(message, language)
    assert reply_text(state) == replies.safety_unavailable(expected_language)
    assert "112" in reply_text(state)
    assert state["safety_verdict"] is None
    assert tool_runs == []
    assert not any(isinstance(m, ToolMessage) for m in state["messages"])
    for table in (ServiceRequest, SymptomLog, Escalation):
        assert await count(session_factory, table) == 0


# ---------- the three verdicts ----------


async def test_emergency_writes_an_escalation_and_nothing_else_runs(
    deps, checkpointer, session_factory, monkeypatch, tool_runs
):
    script(monkeypatch, verdict=SafetyVerdict.EMERGENCY)  # router and reply model must not be called
    graph = build_graph(deps, checkpointer)

    state = await send(
        graph, str(uuid.uuid4()), "my father just collapsed", patient_id="pat_016", society_id="soc_royal"
    )

    assert tool_runs == ["escalate_emergency"]
    assert await count(session_factory, Escalation) == 1
    assert reply_text(state) == replies.emergency(
        Language.EN, hospital="Sanjeevani Hospital", phone="+91 124 4000 1100", minutes=5
    )
    assert state["intents"] == [Intent.EMERGENCY.value]


async def test_medical_advice_is_refused_with_an_offer_to_book(deps, checkpointer, monkeypatch, tool_runs):
    script(monkeypatch, verdict=SafetyVerdict.MEDICAL_ADVICE, language=Language.HINGLISH)
    graph = build_graph(deps, checkpointer)

    state = await send(graph, str(uuid.uuid4()), "bukhar ke liye kaun si dawai lu")

    assert reply_text(state) == replies.medical_advice(Language.HINGLISH)
    assert "book" in reply_text(state)
    assert tool_runs == []


async def test_router_catches_what_the_safety_check_let_through(deps, checkpointer, session_factory, monkeypatch, tool_runs):
    script(monkeypatch, verdict=SafetyVerdict.SAFE, intents=[Intent.EMERGENCY])
    graph = build_graph(deps, checkpointer)

    await send(graph, str(uuid.uuid4()), "saans nahi aa rahi")

    assert tool_runs == ["escalate_emergency"]
    assert await count(session_factory, Escalation) == 1


# ---------- required test 3: restart and continue ----------


async def test_booking_continues_after_a_restart_without_asking_twice(session_factory, embedder, monkeypatch):
    script(monkeypatch, intents=[Intent.BOOK_SERVICE], reply=booking_assistant)
    thread = str(uuid.uuid4())
    settings = get_settings()

    def fresh_deps():
        return Deps(llm=object(), tools=make_tools(session_factory, embedder, min_similarity=get_settings().retrieval_min_similarity), settings=settings)

    # First process: the patient asks to book but gives no date.
    async with open_checkpointer(settings) as first_saver:
        before = await send(build_graph(fresh_deps(), first_saver), thread, "please book me cardiology")
    assert reply_text(before) == "Which date and time would you like?"
    assert await count(session_factory, ServiceRequest) == 0

    # "Restart": the connection pool is closed, and everything is built again from nothing.
    async with open_checkpointer(settings) as second_saver:
        after = await send(build_graph(fresh_deps(), second_saver), thread, "2027-01-12 10:30")

    # The department came from before the restart, the date from after it.
    async with session_factory() as session:
        booking = await session.scalar(select(ServiceRequest))
    assert booking.subtype == "CARDIOLOGY" and booking.clinician_id == "cln_02"
    assert reply_text(after) == "Your appointment is booked."
    # Nothing was asked twice: one question in the whole transcript, and the department never again.
    questions = [m.content for m in after["messages"] if isinstance(m, AIMessage) and m.content.endswith("?")]
    assert questions == ["Which date and time would you like?"]
    assert [m.content for m in after["messages"] if isinstance(m, HumanMessage)] == [
        "please book me cardiology",
        "2027-01-12 10:30",
    ]


# ---------- tools inside the graph ----------


async def test_ids_come_from_the_request_not_from_the_model(deps, checkpointer, session_factory, monkeypatch):
    async def model_tries_another_patient(llm, tools, messages):
        if isinstance(messages[-1], ToolMessage):
            return AIMessage("done")
        return tool_call(
            "book_service", service="DOCTOR", subtype="CARDIOLOGY", scheduled_for="2027-01-12T10:30",
            patient_id="pat_010", request_id=str(uuid.uuid4()),
        )

    script(monkeypatch, intents=[Intent.BOOK_SERVICE], reply=model_tries_another_patient)
    request_id = str(uuid.uuid4())

    await send(build_graph(deps, checkpointer), str(uuid.uuid4()), "book", request_id=request_id)

    async with session_factory() as session:
        booking = await session.scalar(select(ServiceRequest))
    assert booking.patient_id == "pat_001"
    assert str(booking.request_id) == request_id


async def test_tool_call_cap_ends_the_loop(deps, checkpointer, monkeypatch, tool_runs):
    async def never_stops(llm, tools, messages):
        return tool_call("list_service_requests") if tools else AIMessage("Here is what I found.")

    script(monkeypatch, intents=[Intent.LIST_SERVICES], reply=never_stops)

    state = await send(build_graph(deps, checkpointer), str(uuid.uuid4()), "show my bookings")

    cap = deps.settings.max_tool_calls_per_turn
    assert tool_runs == ["list_service_requests"] * cap
    assert state["tool_calls_made"] == cap
    assert reply_text(state) == "Here is what I found."


async def test_model_cannot_use_a_tool_its_intent_does_not_allow(deps, checkpointer, session_factory, monkeypatch, tool_runs):
    async def tries_to_escalate_and_book(llm, tools, messages):
        if isinstance(messages[-1], ToolMessage):
            return AIMessage("ok")
        reply = tool_call("escalate_emergency", transcript="x")
        reply.tool_calls.append(tool_call("book_service", service="DOCTOR", subtype="CARDIOLOGY", scheduled_for="2027-01-12T10:30").tool_calls[0])
        return reply

    script(monkeypatch, intents=[Intent.SMALL_TALK], reply=tries_to_escalate_and_book)

    state = await send(build_graph(deps, checkpointer), str(uuid.uuid4()), "hi")

    assert tool_runs == []
    assert [m.status for m in state["messages"] if isinstance(m, ToolMessage)] == ["error", "error"]
    assert await count(session_factory, Escalation) == 0 and await count(session_factory, ServiceRequest) == 0


async def test_a_tool_that_raises_does_not_break_the_turn(deps, checkpointer, monkeypatch):
    from app import booking

    async def explode(*args, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(booking, "book", explode)
    script(monkeypatch, intents=[Intent.BOOK_SERVICE], reply=booking_assistant)

    state = await send(build_graph(deps, checkpointer), str(uuid.uuid4()), "book cardiology 2027-01-12 10:30")

    assert reply_text(state) == "Could not book."
    failed = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    assert failed.artifact["error"]["code"] == "TOOL_FAILED"
    assert "exploded" not in failed.content


async def test_two_symptoms_in_one_message_are_two_rows(deps, checkpointer, session_factory, monkeypatch):
    async def logs_two(llm, tools, messages):
        if isinstance(messages[-1], ToolMessage):
            return AIMessage("Noted both.")
        reply = tool_call("log_symptom", symptom="headache", severity=2)
        reply.tool_calls.append(tool_call("log_symptom", symptom="cough", severity=3).tool_calls[0])
        return reply

    script(monkeypatch, intents=[Intent.LOG_SYMPTOM], reply=logs_two)
    request_id = str(uuid.uuid4())

    await send(build_graph(deps, checkpointer), str(uuid.uuid4()), "headache 2 and cough 3", request_id=request_id)

    async with session_factory() as session:
        rows = (await session.scalars(select(SymptomLog).order_by(SymptomLog.severity))).all()
    assert [(r.symptom, r.severity) for r in rows] == [("headache", 2), ("cough", 3)]
    assert str(rows[0].request_id) == request_id  # the first write carries the client's id


# ---------- clinic questions ----------


async def test_clinic_answer_is_searched_in_the_patients_society_and_cited(deps, checkpointer, monkeypatch, tool_runs):
    async def answers_from_passages(llm, tools, messages):
        passages = messages[-1].content
        assert "Sunday | Closed" in passages and "09:00 – 13:00" not in passages  # Lotus Tower's hours only
        first = int(re.search(r"\[(\d+)\] Society Annex — Lotus Tower > Wellness room > Hours", passages)[1])
        return AIMessage(f"The wellness room is closed on Sunday [{first}].")

    script(
        monkeypatch,
        language=Language.HI,
        intents=[Intent.CLINIC_INFO],
        search_query="wellness room opening time on Sunday",
        reply=answers_from_passages,
    )

    state = await send(
        build_graph(deps, checkpointer), str(uuid.uuid4()),
        "रविवार को वेलनेस रूम कितने बजे खुलता है?", patient_id="pat_010", society_id="soc_lotus",
    )

    assert tool_runs == ["search_clinic_docs"]
    assert [(c["doc_id"], c["heading_path"]) for c in state["citations"]] == [
        ("annex-lotus-tower", "Society Annex — Lotus Tower > Wellness room > Hours")
    ]


async def test_question_outside_the_corpus_gets_the_fixed_dont_know_reply(deps, checkpointer, monkeypatch, tool_runs):
    # The reply model must not be called: with no evidence there is nothing for it to answer from.
    script(monkeypatch, intents=[Intent.CLINIC_INFO], search_query="who won the cricket match yesterday")

    state = await send(build_graph(deps, checkpointer), str(uuid.uuid4()), "Who won the cricket match yesterday?")

    assert tool_runs == ["search_clinic_docs"]
    assert reply_text(state) == replies.dont_know(Language.EN)
    assert "nurse" in reply_text(state)
    assert state["citations"] == []


async def test_model_says_the_passages_do_not_answer_and_the_patient_gets_the_fixed_reply(deps, checkpointer, monkeypatch):
    async def passages_do_not_answer(llm, tools, messages):
        return AIMessage(f"\n\n{respond.NO_ANSWER}")

    # In-domain wording, so search does return passages; none of them is about a gym.
    script(monkeypatch, intents=[Intent.CLINIC_INFO], search_query="gym timings", reply=passages_do_not_answer)

    state = await send(build_graph(deps, checkpointer), str(uuid.uuid4()), "gym ka timing kya hai", language="hinglish")

    assert reply_text(state) == replies.dont_know(Language.EN)  # the scripted safety check reports English
    assert state["citations"] == []
    assert respond.NO_ANSWER not in "".join(str(m.content) for m in state["messages"])


async def test_medical_intent_from_the_router_does_not_leave_a_search_behind(deps, checkpointer, monkeypatch, tool_runs):
    script(monkeypatch, intents=[Intent.MEDICAL_ADVICE, Intent.CLINIC_INFO], search_query="paracetamol dose")

    state = await send(build_graph(deps, checkpointer), str(uuid.uuid4()), "how much paracetamol is covered and safe")

    assert reply_text(state) == replies.medical_advice(Language.EN)
    assert tool_runs == []
    assert not any(isinstance(m, AIMessage) and m.tool_calls for m in state["messages"])
