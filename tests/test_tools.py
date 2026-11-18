"""The tools as the model will call them: schemas, failures, and writing once."""

import asyncio
import uuid

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool
from sqlalchemy import func, select

from app import booking, records
from app.db.models import Escalation, ServiceRequest, SymptomLog
from app.errors import ConciergeError, ErrorCode
from app.tools import is_error, make_tools, run_tool

TIMEOUT = 5.0


@pytest.fixture
def tools(session_factory, embedder):
    return make_tools(session_factory, embedder, min_similarity=0.36)


async def count(session_factory, model) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(model))


def booking_args(**overrides) -> dict:
    """Arguments as they arrive: plain JSON strings from the model, plus our injected ids."""
    return {
        "patient_id": "pat_001",
        "request_id": str(uuid.uuid4()),
        "service": "DOCTOR",
        "subtype": "CARDIOLOGY",
        "scheduled_for": "2027-01-12T10:30",
        **overrides,
    }


def symptom_args(**overrides) -> dict:
    return {
        "patient_id": "pat_001",
        "request_id": str(uuid.uuid4()),
        "symptom": "sar dard",
        "severity": 3,
        **overrides,
    }


def assert_patient_safe(message: str) -> None:
    for leak in ("Traceback", "IntegrityError", "psycopg", "constraint", "RuntimeError", "exploded"):
        assert leak not in message


# ---------- what the model sees ----------


def test_model_cannot_see_or_set_patient_id_and_request_id(tools):
    for tool in tools:
        visible = convert_to_openai_tool(tool)["function"]["parameters"]["properties"]
        assert "patient_id" not in visible, tool.name
        assert "request_id" not in visible, tool.name
        assert "society_id" not in visible, tool.name


def test_contract_names_and_enum(tools):
    assert [t.name for t in tools] == [
        "book_service",
        "list_service_requests",
        "log_symptom",
        "search_clinic_docs",
        "escalate_emergency",
    ]
    schema = convert_to_openai_tool(tools[0])["function"]["parameters"]
    assert set(schema["required"]) == {"service", "subtype", "scheduled_for"}
    assert "DOCTOR" in str(schema) and "LAB" in str(schema)


# ---------- happy paths ----------


async def test_book_then_list(session_factory, tools):
    booked = await run_tool(tools, "book_service", booking_args(), timeout_s=TIMEOUT)
    listed = await run_tool(tools, "list_service_requests", {"patient_id": "pat_001"}, timeout_s=TIMEOUT)
    other_patient = await run_tool(
        tools, "list_service_requests", {"patient_id": "pat_002"}, timeout_s=TIMEOUT
    )
    cancelled_only = await run_tool(
        tools, "list_service_requests", {"patient_id": "pat_001", "status": "CANCELLED"}, timeout_s=TIMEOUT
    )

    assert booked["clinician_name"] == "Dr. Arvind Khanna"
    assert listed == [booked]
    assert other_patient == []
    assert cancelled_only == []


async def test_escalation_row_and_society_specific_numbers(session_factory, tools):
    # pat_016 is at Royal Palms (Sanjeevani Hospital); pat_010 is at Lotus Tower (Arogya).
    royal = await run_tool(
        tools,
        "escalate_emergency",
        {"patient_id": "pat_016", "request_id": str(uuid.uuid4()), "transcript": "my father collapsed"},
        timeout_s=TIMEOUT,
    )
    lotus = await run_tool(
        tools,
        "escalate_emergency",
        {"patient_id": "pat_010", "request_id": str(uuid.uuid4()), "transcript": "seene mein dard"},
        timeout_s=TIMEOUT,
    )

    assert royal["level"] == 1 and royal["status"] == "OPEN"
    assert royal["call_first"] == "112"
    assert royal["hospital_emergency_phone"] == "+91 124 4000 1100"
    assert lotus["hospital_emergency_phone"] == "+91 120 4555 2200"
    async with session_factory() as session:
        row = await session.scalar(select(Escalation).where(Escalation.patient_id == "pat_016"))
    assert row.society_id == "soc_royal"
    assert row.transcript == "my father collapsed"
    assert 290 <= (row.response_due_at - row.created_at).total_seconds() <= 310  # 5 minutes


# ---------- a write tool called twice with the same request_id ----------


async def test_log_symptom_twice_writes_once(session_factory, tools):
    args = symptom_args()

    first = await run_tool(tools, "log_symptom", args, timeout_s=TIMEOUT)
    second = await run_tool(tools, "log_symptom", args, timeout_s=TIMEOUT)

    assert not is_error(first)
    assert second == first
    assert await count(session_factory, SymptomLog) == 1


async def test_escalate_twice_at_the_same_moment_writes_once(session_factory, tools):
    args = {"patient_id": "pat_016", "request_id": str(uuid.uuid4()), "transcript": "collapsed"}

    first, second = await asyncio.gather(
        run_tool(tools, "escalate_emergency", args, timeout_s=TIMEOUT),
        run_tool(tools, "escalate_emergency", args, timeout_s=TIMEOUT),
    )

    assert second == first
    assert await count(session_factory, Escalation) == 1


async def test_book_twice_writes_once(session_factory, tools):
    args = booking_args()

    first = await run_tool(tools, "book_service", args, timeout_s=TIMEOUT)
    second = await run_tool(tools, "book_service", args, timeout_s=TIMEOUT)

    assert second == first
    assert await count(session_factory, ServiceRequest) == 1


# ---------- a tool called with malformed arguments ----------


@pytest.mark.parametrize(
    "bad, field",
    [
        ({"scheduled_for": "tomorrow morning"}, "scheduled_for"),
        ({"service": "DENTIST"}, "service"),
        ({"scheduled_for": None}, "scheduled_for"),
    ],
)
async def test_malformed_booking_arguments(session_factory, tools, bad, field):
    result = await run_tool(tools, "book_service", booking_args(**bad), timeout_s=TIMEOUT)

    assert result["error"]["code"] == ErrorCode.INVALID_ARGUMENTS.value
    assert field in [f["field"] for f in result["error"]["fields"]]
    assert await count(session_factory, ServiceRequest) == 0


async def test_missing_argument_is_reported_not_invented(session_factory, tools):
    args = booking_args()
    del args["scheduled_for"]

    result = await run_tool(tools, "book_service", args, timeout_s=TIMEOUT)

    assert result["error"]["code"] == ErrorCode.INVALID_ARGUMENTS.value
    assert "scheduled_for" in result["error"]["message"]
    assert await count(session_factory, ServiceRequest) == 0


@pytest.mark.parametrize("severity", [0, 6, "very bad"])
async def test_malformed_severity(session_factory, tools, severity):
    result = await run_tool(tools, "log_symptom", symptom_args(severity=severity), timeout_s=TIMEOUT)

    assert result["error"]["code"] == ErrorCode.INVALID_ARGUMENTS.value
    assert await count(session_factory, SymptomLog) == 0


async def test_unknown_tool_name(tools):
    result = await run_tool(tools, "prescribe_medicine", {}, timeout_s=TIMEOUT)

    assert result["error"]["code"] == ErrorCode.UNKNOWN_TOOL.value


# ---------- a tool that raises ----------


async def test_tool_that_raises_gives_a_clean_error(session_factory, tools, monkeypatch):
    async def explode(*args, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(booking, "book", explode)

    result = await run_tool(tools, "book_service", booking_args(), timeout_s=TIMEOUT)

    assert result["error"]["code"] == ErrorCode.TOOL_FAILED.value
    assert_patient_safe(result["error"]["message"])
    assert await count(session_factory, ServiceRequest) == 0


async def test_tool_that_hangs_is_stopped_by_the_timeout(tools, monkeypatch):
    async def hang(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(booking, "book", hang)

    result = await run_tool(tools, "book_service", booking_args(), timeout_s=0.1)

    assert result["error"]["code"] == ErrorCode.TOOL_TIMEOUT.value


async def test_expected_refusal_keeps_its_message_and_suggestions(tools):
    await run_tool(tools, "book_service", booking_args(), timeout_s=TIMEOUT)

    result = await run_tool(tools, "book_service", booking_args(patient_id="pat_002"), timeout_s=TIMEOUT)

    assert result["error"]["code"] == ErrorCode.SLOT_TAKEN.value
    assert result["error"]["suggestions"][0]["scheduled_for"] == "2027-01-12T10:00:00+05:30"
    assert_patient_safe(result["error"]["message"])


# ---------- the database rule, with the Pydantic check out of the way ----------


async def test_database_rejects_severity_6_with_a_clear_sentence(session_factory):
    """Calls the write directly, skipping the tool schema, so only Postgres can stop it."""
    with pytest.raises(ConciergeError) as refused:
        await records.log_symptom(
            session_factory, patient_id="pat_001", symptom="cough", severity=6, request_id=uuid.uuid4()
        )

    assert refused.value.code == ErrorCode.INVALID_SEVERITY
    assert refused.value.message == "Severity must be a number from 1 (mild) to 5 (severe)."
    assert await count(session_factory, SymptomLog) == 0
