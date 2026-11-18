"""Booking rules: the slot grid, picking the clinician, and writing the row.

Python decides whether a request makes sense (known subtype, a real slot).
The DATABASE decides who wins a slot: we just INSERT and let the partial
unique index reject the loser. There is no "check if free, then insert",
because two requests can both pass that check in the same instant.
"""

import uuid
from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import scoping
from app.contract import Service
from app.errors import ConciergeError, ErrorCode, violated_constraint
from app.db.models import UQ_ACTIVE_SLOT, Clinician, ServiceRequest, Society

WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]  # date.weekday() order
SUGGESTION_DAYS = 14  # how far ahead to look for free slots to offer
SUGGESTION_LIMIT = 3


class BookingStatus(str, Enum):
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"


# ---------- slot grid (pure functions, no database) ----------


def slots_on(clinician: Clinician, society_id: str, day: date, tz: ZoneInfo) -> list[datetime]:
    """Slot starts for one clinician at one society on one day.

    A window 10:00-11:00 with 30-minute slots gives 10:00 and 10:30.
    """
    step = timedelta(minutes=clinician.slot_minutes)
    slots: list[datetime] = []
    for window in clinician.availability:
        if window["society_id"] != society_id or window["weekday"] != WEEKDAYS[day.weekday()]:
            continue
        start = datetime.combine(day, time.fromisoformat(window["start"]), tz)
        end = datetime.combine(day, time.fromisoformat(window["end"]), tz)
        while start + step <= end:
            slots.append(start)
            start += step
    return slots


def _fmt(when: datetime) -> str:
    return when.strftime("%a %d %b %Y, %H:%M")


# ---------- database helpers ----------


async def _subtype_exists(session: AsyncSession, service: Service, subtype: str) -> bool:
    query = select(Clinician.id).where(
        Clinician.service == service.value, Clinician.subtypes.any(subtype)
    )
    return (await session.execute(query.limit(1))).first() is not None


async def _free_slots_near(
    session: AsyncSession,
    *,
    society_id: str,
    clinician: Clinician,
    tz: ZoneInfo,
    wanted: datetime,
) -> list[dict]:
    """The free slots closest to the requested time, same clinician, from that day on."""
    first_day = wanted.date()
    grid = [
        slot
        for offset in range(SUGGESTION_DAYS)
        for slot in slots_on(clinician, society_id, first_day + timedelta(days=offset), tz)
    ]
    if not grid:
        return []
    taken = await scoping.booked_times(
        session,
        society_id=society_id,
        clinician_id=clinician.id,
        start=grid[0],
        end=grid[-1] + timedelta(minutes=1),
    )
    free = [slot for slot in grid if slot not in taken and slot != wanted]
    nearest = sorted(free, key=lambda slot: abs(slot - wanted))[:SUGGESTION_LIMIT]
    return [
        {"clinician_name": clinician.name, "scheduled_for": slot.isoformat(), "label": _fmt(slot)}
        for slot in sorted(nearest)
    ]


def _with_suggestions(sentence: str, suggestions: list[dict]) -> str:
    if not suggestions:
        return sentence
    return f"{sentence} Nearest free slots: {'; '.join(s['label'] for s in suggestions)}."


# ---------- the booking itself ----------


async def book(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    patient_id: str,
    service: Service,
    subtype: str,
    scheduled_for: datetime,
    request_id: uuid.UUID,
) -> dict:
    """Create a booking, or return the existing one if this request_id was seen before.

    Raises ConciergeError with a patient-readable message when the booking is refused.
    """
    async with session_factory() as session:
        patient = await scoping.get_patient(session, patient_id)
        if patient is None:
            raise ConciergeError(ErrorCode.PATIENT_NOT_FOUND, "We could not find that patient.")
        society_id = patient.society_id

        # A repeated request: report the first result, write nothing.
        existing = await scoping.find_booking_by_request_id(
            session, society_id=society_id, patient_id=patient_id, request_id=request_id
        )
        if existing:
            return existing

        society = await session.get(Society, society_id)
        tz = ZoneInfo(society.timezone)
        # A time without a timezone means "local time at the society".
        wanted = (
            scheduled_for.replace(tzinfo=tz)
            if scheduled_for.tzinfo is None
            else scheduled_for.astimezone(tz)
        )

        if not await _subtype_exists(session, service, subtype):
            raise ConciergeError(
                ErrorCode.UNKNOWN_SUBTYPE,
                f"'{subtype}' is not a {service.value} service we know.",
            )

        clinicians = await scoping.clinicians_offering(
            session, society_id=society_id, service=service, subtype=subtype
        )
        if not clinicians:
            raise ConciergeError(
                ErrorCode.NOT_OFFERED_AT_SOCIETY,
                f"{subtype} is not offered at {society.name}.",
            )

        # Keep only clinicians for whom the requested time is a real slot start.
        on_grid = [c for c in clinicians if wanted in slots_on(c, society_id, wanted.date(), tz)]
        if not on_grid:
            suggestions = await _free_slots_near(
                session, society_id=society_id, clinician=clinicians[0], tz=tz, wanted=wanted
            )
            raise ConciergeError(
                ErrorCode.NOT_A_SLOT,
                _with_suggestions(
                    f"{clinicians[0].name} has no slot starting at {_fmt(wanted)}.", suggestions
                ),
                suggestions,
            )

    # Try to take the slot. The database is the judge.
    for clinician in on_grid:
        try:
            async with session_factory() as session, session.begin():
                row = ServiceRequest(
                    patient_id=patient_id,
                    society_id=society_id,
                    clinician_id=clinician.id,
                    service=service.value,
                    subtype=subtype,
                    scheduled_for=wanted,
                    status=BookingStatus.BOOKED.value,
                    request_id=request_id,
                )
                session.add(row)
                await session.flush()  # sends the INSERT; raises here if a rule is broken
                return scoping.booking_to_dict(row, clinician.name, society.timezone)
        except IntegrityError as exc:
            # Was it our own request arriving twice at the same moment?
            async with session_factory() as session:
                existing = await scoping.find_booking_by_request_id(
                    session, society_id=society_id, patient_id=patient_id, request_id=request_id
                )
            if existing:
                return existing
            if violated_constraint(exc) != UQ_ACTIVE_SLOT:
                raise ConciergeError(
                    ErrorCode.REQUEST_ID_REUSED,
                    "This request was already used for a different booking. Please send it again.",
                ) from exc
            # Otherwise the slot was taken: try the next clinician, if any.

    async with session_factory() as session:
        suggestions = await _free_slots_near(
            session, society_id=society_id, clinician=on_grid[0], tz=tz, wanted=wanted
        )
    raise ConciergeError(
        ErrorCode.SLOT_TAKEN,
        _with_suggestions(
            f"The {_fmt(wanted)} slot with {on_grid[0].name} has just been taken.", suggestions
        ),
        suggestions,
    )
