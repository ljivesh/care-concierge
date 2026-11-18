"""The two other writes: logging a symptom and raising an emergency escalation.

Both are idempotent on request_id the same way: INSERT ... ON CONFLICT DO
NOTHING, then read the row back. A repeated request finds the first row and
writes nothing new.
"""

import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import scoping
from app.db.models import (
    CK_SEVERITY,
    UQ_ESCALATION_REQUEST_ID,
    UQ_SYMPTOM_REQUEST_ID,
    Escalation,
    Patient,
    Society,
    SymptomLog,
)
from app.errors import ConciergeError, ErrorCode, violated_constraint

# From the escalation SLA document: Level 1 (critical) gets a nurse callback in 5 minutes.
# The concierge always raises Level 1; only a nurse may downgrade.
CONCIERGE_LEVEL = 1
LEVEL_1_CALLBACK_MINUTES = 5
NATIONAL_EMERGENCY_NUMBER = "112"


async def _require_patient(session: AsyncSession, patient_id: str) -> Patient:
    patient = await scoping.get_patient(session, patient_id)
    if patient is None:
        raise ConciergeError(ErrorCode.PATIENT_NOT_FOUND, "We could not find that patient.")
    return patient


def _check_owner(row_patient_id: str, patient_id: str) -> None:
    if row_patient_id != patient_id:
        raise ConciergeError(
            ErrorCode.REQUEST_ID_REUSED,
            "This request was already used for something else. Please send it again.",
        )


async def log_symptom(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    patient_id: str,
    symptom: str,
    severity: int,
    request_id: uuid.UUID,
) -> dict:
    try:
        async with session_factory() as session, session.begin():
            await _require_patient(session, patient_id)
            await session.execute(
                insert(SymptomLog)
                .values(patient_id=patient_id, symptom=symptom, severity=severity, request_id=request_id)
                .on_conflict_do_nothing(constraint=UQ_SYMPTOM_REQUEST_ID)
            )
    except IntegrityError as exc:
        # The database's CHECK is the rule; this turns its rejection into a sentence.
        if violated_constraint(exc) == CK_SEVERITY:
            raise ConciergeError(
                ErrorCode.INVALID_SEVERITY,
                "Severity must be a number from 1 (mild) to 5 (severe).",
            ) from exc
        raise

    async with session_factory() as session:
        row = await session.scalar(select(SymptomLog).where(SymptomLog.request_id == request_id))
    _check_owner(row.patient_id, patient_id)
    return {
        "id": str(row.id),
        "patient_id": row.patient_id,
        "symptom": row.symptom,
        "severity": row.severity,
        "request_id": str(row.request_id),
    }


async def raise_escalation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    patient_id: str,
    transcript: str,
    request_id: uuid.UUID,
) -> dict:
    """Store an emergency for the care team. Returns the row plus the numbers the
    patient should call, taken from their own society's record."""
    async with session_factory() as session, session.begin():
        patient = await _require_patient(session, patient_id)
        await session.execute(
            insert(Escalation)
            .values(
                patient_id=patient_id,
                society_id=patient.society_id,
                level=CONCIERGE_LEVEL,
                transcript=transcript,
                # Deadline is computed by the database clock, from the moment it is raised.
                response_due_at=func.now() + timedelta(minutes=LEVEL_1_CALLBACK_MINUTES),
                request_id=request_id,
            )
            .on_conflict_do_nothing(constraint=UQ_ESCALATION_REQUEST_ID)
        )

    async with session_factory() as session:
        row, society = (
            await session.execute(
                select(Escalation, Society)
                .join(Society, Society.id == Escalation.society_id)
                .where(Escalation.request_id == request_id)
            )
        ).one()
    _check_owner(row.patient_id, patient_id)
    return {
        "id": str(row.id),
        "patient_id": row.patient_id,
        "society_id": row.society_id,
        "level": row.level,
        "status": row.status,
        "response_due_at": row.response_due_at.astimezone(ZoneInfo(society.timezone)).isoformat(),
        "nurse_callback_minutes": LEVEL_1_CALLBACK_MINUTES,
        "call_first": NATIONAL_EMERGENCY_NUMBER,
        "hospital_name": society.hospital_name,
        "hospital_emergency_phone": society.hospital_emergency_phone,
        "request_id": str(row.request_id),
    }
