"""The LangChain tools, with the names and arguments fixed by the contract.

Three ideas in this file:

1. Each tool has a Pydantic class describing its arguments. LangChain turns
   that class into the JSON schema the model sees, and validates the model's
   arguments against it before our code runs.

2. `patient_id` and `request_id` are marked InjectedToolArg. They are hidden
   from the model: it cannot see them, so it cannot invent them. Our code
   fills them in from the request.

3. `run_tool` is the only way a tool gets called. It adds the timeout and
   turns every kind of failure into the same {"error": {...}} shape, so one
   broken tool call can never crash a turn.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Annotated, Any

from langchain_core.tools import BaseTool, InjectedToolArg, StructuredTool
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import booking, records, scoping
from app.booking import BookingStatus
from app.contract import Service
from app.embeddings import Embedder
from app.errors import ConciergeError, ErrorCode

log = logging.getLogger("concierge.tools")

# ---------- argument schemas ----------

PatientId = Annotated[str, InjectedToolArg]
RequestId = Annotated[uuid.UUID, InjectedToolArg]
# Also hidden from the model: which society's documents may be searched is not its choice.
SocietyId = Annotated[str, InjectedToolArg]


class BookServiceArgs(BaseModel):
    patient_id: PatientId
    service: Service = Field(description="DOCTOR for a consultation or physiotherapy, LAB for a lab test.")
    subtype: str = Field(
        description=(
            "Department or test code from the directory. DOCTOR: GENERAL_PHYSICIAN, CARDIOLOGY, "
            "PAEDIATRICS, ORTHOPAEDICS, DERMATOLOGY, ENT, GYNAECOLOGY, PHYSIOTHERAPY. "
            "LAB: CBC, FASTING_BLOOD_SUGAR, HBA1C, LIPID_PROFILE, LFT, KFT, THYROID_PROFILE, "
            "VITAMIN_D, URINE_ROUTINE."
        )
    )
    scheduled_for: datetime = Field(
        description=(
            "Slot start as local date and time, e.g. 2027-01-12T10:30. Use only a date and time "
            "the patient stated. If either is missing, ask the patient instead of calling this tool."
        )
    )
    request_id: RequestId


class ListServiceRequestsArgs(BaseModel):
    patient_id: PatientId
    status: BookingStatus | None = Field(default=None, description="Leave empty for all bookings.")


class LogSymptomArgs(BaseModel):
    patient_id: PatientId
    symptom: str = Field(min_length=1, description="The symptom in the patient's own words.")
    severity: int = Field(
        ge=1,
        le=5,
        description="1 (mild) to 5 (severe), as stated by the patient. Ask if they did not say.",
    )
    request_id: RequestId


class EscalateEmergencyArgs(BaseModel):
    patient_id: PatientId
    transcript: str = Field(min_length=1, description="The patient's message that triggered the escalation.")
    request_id: RequestId


class SearchClinicDocsArgs(BaseModel):
    query: str = Field(
        min_length=1,
        description="What the patient wants to know about the clinic, as a short search query in English.",
    )
    society_id: SocietyId
    k: int = Field(default=6, ge=1, le=10, description="How many passages to return.")


# ---------- the tools ----------


def make_tools(
    session_factory: async_sessionmaker[AsyncSession], embedder: Embedder, *, min_similarity: float
) -> list[BaseTool]:
    """Build the tools around their dependencies. A function, not module-level
    objects, so nothing global is shared and tests can pass their own database."""

    async def book_service(
        patient_id: str, service: Service, subtype: str, scheduled_for: datetime, request_id: uuid.UUID
    ) -> dict:
        return await booking.book(
            session_factory,
            patient_id=patient_id,
            service=service,
            subtype=subtype,
            scheduled_for=scheduled_for,
            request_id=request_id,
        )

    async def list_service_requests(patient_id: str, status: BookingStatus | None = None) -> list[dict]:
        async with session_factory() as session:
            patient = await scoping.get_patient(session, patient_id)
            if patient is None:
                raise ConciergeError(ErrorCode.PATIENT_NOT_FOUND, "We could not find that patient.")
            return await scoping.list_bookings(
                session,
                society_id=patient.society_id,
                patient_id=patient_id,
                status=status.value if status else None,
            )

    async def log_symptom(patient_id: str, symptom: str, severity: int, request_id: uuid.UUID) -> dict:
        return await records.log_symptom(
            session_factory,
            patient_id=patient_id,
            symptom=symptom,
            severity=severity,
            request_id=request_id,
        )

    async def escalate_emergency(patient_id: str, transcript: str, request_id: uuid.UUID) -> dict:
        return await records.raise_escalation(
            session_factory, patient_id=patient_id, transcript=transcript, request_id=request_id
        )

    async def search_clinic_docs(query: str, society_id: str, k: int = 6) -> list[dict]:
        (query_embedding,) = await embedder.embed([query])
        async with session_factory() as session:
            passages = await scoping.search_chunks(
                session, society_id=society_id, query_embedding=query_embedding, k=k
            )
        # Abstention: passages below the threshold are not evidence. An empty
        # list tells the agent to say it does not know and offer a nurse.
        return [p for p in passages if p["similarity"] >= min_similarity]

    return [
        StructuredTool.from_function(
            coroutine=book_service,
            name="book_service",
            description="Book a doctor consultation or a lab test for the patient at a slot start time.",
            args_schema=BookServiceArgs,
        ),
        StructuredTool.from_function(
            coroutine=list_service_requests,
            name="list_service_requests",
            description="List the patient's bookings, optionally filtered by status.",
            args_schema=ListServiceRequestsArgs,
        ),
        StructuredTool.from_function(
            coroutine=log_symptom,
            name="log_symptom",
            description="Record a symptom the patient wants the care team to know about.",
            args_schema=LogSymptomArgs,
        ),
        StructuredTool.from_function(
            coroutine=search_clinic_docs,
            name="search_clinic_docs",
            description=(
                "Search MicroHeal's published documents for the patient's society. The only source "
                "for clinic questions (hours, coverage, fees, test preparation, policies)."
            ),
            args_schema=SearchClinicDocsArgs,
        ),
        StructuredTool.from_function(
            coroutine=escalate_emergency,
            name="escalate_emergency",
            description="Raise an emergency escalation to the care team. Never called by the model directly.",
            args_schema=EscalateEmergencyArgs,
        ),
    ]


# ---------- calling a tool safely ----------


def error_result(code: ErrorCode, message: str, **extra: Any) -> dict:
    return {"error": {"code": code.value, "message": message, **extra}}


def is_error(result: Any) -> bool:
    return isinstance(result, dict) and "error" in result


async def run_tool(
    tools: list[BaseTool], name: str, args: dict, *, timeout_s: float
) -> dict | list[dict]:
    """Call one tool. Always returns a result; never raises.

    On success: whatever the tool returns. On any failure: {"error": {code, message}}.
    """
    tool = next((t for t in tools if t.name == name), None)
    if tool is None:
        return error_result(ErrorCode.UNKNOWN_TOOL, f"There is no tool called '{name}'.")

    try:
        return await asyncio.wait_for(tool.ainvoke(args), timeout=timeout_s)
    except ConciergeError as exc:
        # An expected refusal (slot taken, not offered...). The message is already patient-ready.
        return error_result(exc.code, exc.message, suggestions=exc.suggestions)
    except ValidationError as exc:
        # The model sent arguments that do not match the schema.
        problems = [
            {"field": ".".join(str(part) for part in err["loc"]), "problem": err["msg"]}
            for err in exc.errors()
        ]
        summary = "; ".join(f"{p['field']}: {p['problem']}" for p in problems)
        return error_result(ErrorCode.INVALID_ARGUMENTS, f"Invalid arguments. {summary}", fields=problems)
    except asyncio.TimeoutError:
        log.error("tool_timeout name=%s timeout_s=%s", name, timeout_s)
        return error_result(
            ErrorCode.TOOL_TIMEOUT,
            "That took too long and was stopped. Please try again, or ask to speak to a nurse.",
        )
    except Exception:
        # Anything unexpected: keep the details in the log, not in front of the patient.
        log.exception("tool_failed name=%s", name)
        return error_result(
            ErrorCode.TOOL_FAILED,
            "Something went wrong on our side. Please try again, or ask to speak to a nurse.",
        )
