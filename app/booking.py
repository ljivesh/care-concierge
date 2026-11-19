"""Booking rules: the slot grid, picking the clinician, and writing, moving or cancelling the row.

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
SLOT_LIST_DAYS = 14  # how far ahead find_available_slots looks
SLOT_LIST_LIMIT = 12
# From the clinic policy: a booking needs 2 hours' notice, and can be cancelled or
# rescheduled free of charge up to 2 hours before the slot.
NOTICE = timedelta(hours=2)
WELLNESS_ROOM = "please call your wellness room"


def current_time(tz: ZoneInfo) -> datetime:
    """The clock, in one place, so tests can set it."""
    return datetime.now(tz)


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
    earliest: datetime,
) -> list[dict]:
    """The free slots closest to the requested time, same clinician, none before `earliest`."""
    first_day = max(wanted, earliest).date()
    grid = [
        slot
        for offset in range(SUGGESTION_DAYS)
        for slot in slots_on(clinician, society_id, first_day + timedelta(days=offset), tz)
        if slot >= earliest
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
    return [_slot(clinician, slot) for slot in sorted(nearest)]


def _refuse_if_too_early(wanted: datetime, now: datetime, suggestions: list[dict]) -> None:
    """A slot in the past, or less than 2 hours away, cannot be booked here."""
    if wanted <= now:
        raise ConciergeError(
            ErrorCode.PAST_SLOT,
            _with_suggestions(f"{_fmt(wanted)} has already passed.", suggestions),
            suggestions,
        )
    if wanted < now + NOTICE:
        raise ConciergeError(
            ErrorCode.TOO_SOON,
            _with_suggestions(
                f"Bookings need at least 2 hours' notice. For {_fmt(wanted)}, {WELLNESS_ROOM}.", suggestions
            ),
            suggestions,
        )


def _with_suggestions(sentence: str, suggestions: list[dict]) -> str:
    if not suggestions:
        return sentence
    return f"{sentence} Nearest free slots: {'; '.join(s['label'] for s in suggestions)}."


async def _clinicians_or_refuse(
    session: AsyncSession, society: Society, service: Service, subtype: str
) -> list[Clinician]:
    """The clinicians who can do this at the patient's society, or a clear refusal."""
    if not await _subtype_exists(session, service, subtype):
        raise ConciergeError(
            ErrorCode.UNKNOWN_SUBTYPE, f"'{subtype}' is not a {service.value} service we know."
        )
    clinicians = await scoping.clinicians_offering(
        session, society_id=society.id, service=service, subtype=subtype
    )
    if not clinicians:
        raise ConciergeError(
            ErrorCode.NOT_OFFERED_AT_SOCIETY, f"{subtype} is not offered at {society.name}."
        )
    return clinicians


def _slot(clinician: Clinician, when: datetime) -> dict:
    return {"clinician_name": clinician.name, "scheduled_for": when.isoformat(), "label": _fmt(when)}


# ---------- free slots (read only) ----------


async def available_slots(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    patient_id: str,
    service: Service,
    subtype: str,
    start: date | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Upcoming free slots for a department or test at the patient's society, soonest first.

    Looks SLOT_LIST_DAYS ahead from `start` (today if not given). Slots in the past, or less
    than 2 hours away, are not offered.
    """
    async with session_factory() as session:
        patient = await scoping.get_patient(session, patient_id)
        if patient is None:
            raise ConciergeError(ErrorCode.PATIENT_NOT_FOUND, "We could not find that patient.")
        society = await session.get(Society, patient.society_id)
        tz = ZoneInfo(society.timezone)
        clinicians = await _clinicians_or_refuse(session, society, service, subtype)

        now = (now or current_time(tz)).astimezone(tz)
        earliest = now + NOTICE  # nothing sooner can be booked, so nothing sooner is offered
        first_day = max(start or now.date(), now.date())
        free: list[tuple[datetime, Clinician]] = []
        for clinician in clinicians:
            grid = [
                slot
                for offset in range(SLOT_LIST_DAYS)
                for slot in slots_on(clinician, society.id, first_day + timedelta(days=offset), tz)
                if slot >= earliest
            ]
            if not grid:
                continue
            taken = await scoping.booked_times(
                session,
                society_id=society.id,
                clinician_id=clinician.id,
                start=grid[0],
                end=grid[-1] + timedelta(minutes=1),
            )
            free += [(slot, clinician) for slot in grid if slot not in taken]

    free.sort(key=lambda pair: pair[0])
    return [_slot(clinician, when) for when, clinician in free[:SLOT_LIST_LIMIT]]


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

        clinicians = await _clinicians_or_refuse(session, society, service, subtype)

        now = current_time(tz)
        earliest = now + NOTICE
        if wanted < earliest:
            suggestions = await _free_slots_near(
                session, society_id=society_id, clinician=clinicians[0], tz=tz, wanted=wanted, earliest=earliest
            )
            _refuse_if_too_early(wanted, now, suggestions)

        # Keep only clinicians for whom the requested time is a real slot start.
        on_grid = [c for c in clinicians if wanted in slots_on(c, society_id, wanted.date(), tz)]
        if not on_grid:
            suggestions = await _free_slots_near(
                session, society_id=society_id, clinician=clinicians[0], tz=tz, wanted=wanted, earliest=earliest
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
                # Or does this patient already hold the slot? That happens when they
                # send the same booking again as a new message (a new request_id),
                # for example after never seeing the first reply. Tell them it is
                # theirs, not that "someone" took it.
                mine = await scoping.find_own_active_booking(
                    session,
                    society_id=society_id,
                    patient_id=patient_id,
                    clinician_id=clinician.id,
                    scheduled_for=wanted,
                )
            if mine:
                return {**mine, "already_booked": True}
            if violated_constraint(exc) != UQ_ACTIVE_SLOT:
                raise ConciergeError(
                    ErrorCode.REQUEST_ID_REUSED,
                    "This request was already used for a different booking. Please send it again.",
                ) from exc
            # Otherwise the slot was taken: try the next clinician, if any.

    async with session_factory() as session:
        suggestions = await _free_slots_near(
            session, society_id=society_id, clinician=on_grid[0], tz=tz, wanted=wanted, earliest=earliest
        )
    raise ConciergeError(
        ErrorCode.SLOT_TAKEN,
        _with_suggestions(
            f"The {_fmt(wanted)} slot with {on_grid[0].name} has just been taken.", suggestions
        ),
        suggestions,
    )


# ---------- changing a booking ----------


async def _own_booking(session: AsyncSession, patient_id: str, booking_id: uuid.UUID):
    """The patient, their society, and the booking row, locked for this transaction.
    The row is looked up by the patient's own id and society, so a booking id that
    belongs to someone else is simply "not found"."""
    patient = await scoping.get_patient(session, patient_id)
    if patient is None:
        raise ConciergeError(ErrorCode.PATIENT_NOT_FOUND, "We could not find that patient.")
    society = await session.get(Society, patient.society_id)
    row = await session.scalar(
        select(ServiceRequest)
        .where(
            ServiceRequest.id == booking_id,
            ServiceRequest.patient_id == patient_id,
            ServiceRequest.society_id == patient.society_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ConciergeError(ErrorCode.BOOKING_NOT_FOUND, "We could not find that booking.")
    clinician = await session.get(Clinician, row.clinician_id)
    return society, row, clinician


async def cancel(
    session_factory: async_sessionmaker[AsyncSession], *, patient_id: str, booking_id: uuid.UUID
) -> dict:
    """Cancel one of the patient's bookings. Cancelling twice is harmless.

    Up to 2 hours before the slot it is free. Later than that it still frees the
    slot, but the policy counts it as a no-show, and the result says so.
    """
    async with session_factory() as session, session.begin():
        society, row, clinician = await _own_booking(session, patient_id, booking_id)
        tz = ZoneInfo(society.timezone)
        if row.status in (BookingStatus.CANCELLED.value, BookingStatus.NO_SHOW.value):
            return {**scoping.booking_to_dict(row, clinician.name, society.timezone), "already_cancelled": True}
        now = current_time(tz)
        if row.status != BookingStatus.BOOKED.value or row.scheduled_for <= now:
            raise ConciergeError(ErrorCode.NOT_ACTIVE, "That appointment has already taken place.")

        late = row.scheduled_for < now + NOTICE
        row.status = (BookingStatus.NO_SHOW if late else BookingStatus.CANCELLED).value
        return {
            **scoping.booking_to_dict(row, clinician.name, society.timezone),
            "cancelled": True,
            "late_cancellation": late,  # True: inside the 2-hour window, counted as a no-show
        }


async def reschedule(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    patient_id: str,
    booking_id: uuid.UUID,
    scheduled_for: datetime,
) -> dict:
    """Move one of the patient's bookings to another slot with the same clinician.

    The same row is updated, so the unique index still decides whether the new
    slot is free, and asking for the same move twice changes nothing.
    """
    try:
        async with session_factory() as session, session.begin():
            society, row, clinician = await _own_booking(session, patient_id, booking_id)
            tz = ZoneInfo(society.timezone)
            now = current_time(tz)
            earliest = now + NOTICE
            wanted = scheduled_for.replace(tzinfo=tz) if scheduled_for.tzinfo is None else scheduled_for.astimezone(tz)
            previous = row.scheduled_for.astimezone(tz)

            if row.status != BookingStatus.BOOKED.value:
                raise ConciergeError(ErrorCode.NOT_ACTIVE, "That booking is no longer active, so it cannot be moved.")
            if wanted == previous:
                return {**scoping.booking_to_dict(row, clinician.name, society.timezone), "unchanged": True}
            if previous < earliest:
                raise ConciergeError(
                    ErrorCode.TOO_LATE_TO_CHANGE,
                    f"This appointment is less than 2 hours away, so it can no longer be moved here. "
                    f"To change it, {WELLNESS_ROOM}.",
                )

            async def suggestions() -> list[dict]:
                return await _free_slots_near(
                    session, society_id=society.id, clinician=clinician, tz=tz, wanted=wanted, earliest=earliest
                )

            if wanted < earliest:
                _refuse_if_too_early(wanted, now, await suggestions())
            if wanted not in slots_on(clinician, society.id, wanted.date(), tz):
                offered = await suggestions()
                raise ConciergeError(
                    ErrorCode.NOT_A_SLOT,
                    _with_suggestions(f"{clinician.name} has no slot starting at {_fmt(wanted)}.", offered),
                    offered,
                )

            # Plain values, kept for the error path: once the UPDATE is rejected the
            # transaction is rolled back and these objects can no longer be read.
            society_id, clinician_id = society.id, clinician.id
            row.scheduled_for = wanted
            await session.flush()  # sends the UPDATE; the slot index rejects it if the slot is held
            return {
                **scoping.booking_to_dict(row, clinician.name, society.timezone),
                "rescheduled": True,
                "previous_scheduled_for": previous.isoformat(),
            }
    except IntegrityError as exc:
        if violated_constraint(exc) != UQ_ACTIVE_SLOT:
            raise
        async with session_factory() as session:
            clinician = await session.get(Clinician, clinician_id)
            offered = await _free_slots_near(
                session, society_id=society_id, clinician=clinician, tz=tz, wanted=wanted, earliest=earliest
            )
            name = clinician.name
        raise ConciergeError(
            ErrorCode.SLOT_TAKEN,
            _with_suggestions(f"The {_fmt(wanted)} slot with {name} is already taken.", offered),
            offered,
        ) from exc
