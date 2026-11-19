"""Booking rules, against a real Postgres. Two of the three required tests live here:
concurrent double-booking and the duplicate request."""

import asyncio
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, update

from app.booking import book, slots_on
from app.errors import ConciergeError, ErrorCode
from app.contract import Service
from app.db.models import Clinician, ServiceRequest

IST = ZoneInfo("Asia/Kolkata")
# Dr. Arvind Khanna (cln_02) is at Shivalik Greens on Tuesdays 10:00-11:00, 30-minute slots.
TUESDAY_1030 = datetime(2027, 1, 12, 10, 30, tzinfo=IST)
SHIVALIK_PATIENTS = [f"pat_00{n}" for n in range(1, 9)]


def cardiology(patient_id: str, when: datetime = TUESDAY_1030, request_id: uuid.UUID | None = None):
    return dict(
        patient_id=patient_id,
        service=Service.DOCTOR,
        subtype="CARDIOLOGY",
        scheduled_for=when,
        request_id=request_id or uuid.uuid4(),
    )


async def count_bookings(session_factory) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(ServiceRequest))


def assert_clear_sentence(message: str) -> None:
    """What the patient reads must not leak database or Python internals."""
    for leak in ("IntegrityError", "duplicate key", "constraint", "Traceback", "psycopg"):
        assert leak not in message


# ---------- required test 1: concurrent double-booking ----------


async def test_two_simultaneous_bookings_one_row_one_clear_error(session_factory):
    results = await asyncio.gather(
        book(session_factory, **cardiology("pat_001")),
        book(session_factory, **cardiology("pat_002")),
        return_exceptions=True,
    )

    winners = [r for r in results if isinstance(r, dict)]
    losers = [r for r in results if isinstance(r, ConciergeError)]
    assert len(winners) == 1 and len(losers) == 1, results
    assert await count_bookings(session_factory) == 1

    assert losers[0].code == ErrorCode.SLOT_TAKEN
    assert "taken" in losers[0].message
    assert_clear_sentence(losers[0].message)


async def test_eight_simultaneous_bookings_still_one_row(session_factory):
    results = await asyncio.gather(
        *(book(session_factory, **cardiology(p)) for p in SHIVALIK_PATIENTS),
        return_exceptions=True,
    )

    assert sum(isinstance(r, dict) for r in results) == 1
    assert all(
        isinstance(r, dict) or (isinstance(r, ConciergeError) and r.code == ErrorCode.SLOT_TAKEN)
        for r in results
    ), results
    assert await count_bookings(session_factory) == 1


# ---------- required test 2: duplicate request ----------


async def test_same_request_id_twice_one_row_same_booking(session_factory):
    request = cardiology("pat_001")

    first = await book(session_factory, **request)
    second = await book(session_factory, **request)

    assert second == first
    assert await count_bookings(session_factory) == 1


async def test_same_request_id_at_the_same_moment_one_row_same_booking(session_factory):
    request = cardiology("pat_001")

    first, second = await asyncio.gather(
        book(session_factory, **request), book(session_factory, **request)
    )

    assert second == first
    assert await count_bookings(session_factory) == 1


async def test_request_id_of_another_patient_is_refused_not_leaked(session_factory):
    shared_id = uuid.uuid4()
    await book(session_factory, **cardiology("pat_001", request_id=shared_id))

    with pytest.raises(ConciergeError) as refused:
        await book(
            session_factory,
            **cardiology("pat_002", when=TUESDAY_1030.replace(minute=0), request_id=shared_id),
        )

    assert refused.value.code == ErrorCode.REQUEST_ID_REUSED
    assert_clear_sentence(refused.value.message)
    assert await count_bookings(session_factory) == 1


# ---------- slot grid and clinician lookup ----------


async def test_slot_grid_matches_the_bundle_example(session_factory):
    async with session_factory() as session:
        khanna = await session.get(Clinician, "cln_02")
        physio = await session.get(Clinician, "cln_07")

    tuesday = date(2027, 1, 12)
    assert [s.strftime("%H:%M") for s in slots_on(khanna, "soc_shivalik", tuesday, IST)] == [
        "10:00",
        "10:30",
    ]
    # 17:00-18:30 with 45-minute slots: two slots, nothing left over.
    assert [s.strftime("%H:%M") for s in slots_on(physio, "soc_shivalik", tuesday, IST)] == [
        "17:00",
        "17:45",
    ]
    # He is at Royal Palms on Thursdays, not Tuesdays.
    assert slots_on(khanna, "soc_royal", tuesday, IST) == []


async def test_booking_picks_the_clinician_and_society_from_the_patient(session_factory):
    booking = await book(session_factory, **cardiology("pat_001"))

    assert booking["clinician_id"] == "cln_02"
    assert booking["society_id"] == "soc_shivalik"
    assert booking["status"] == "BOOKED"
    assert booking["scheduled_for"] == "2027-01-12T10:30:00+05:30"


async def test_time_off_the_slot_grid_is_refused_with_free_slots(session_factory):
    with pytest.raises(ConciergeError) as refused:
        await book(session_factory, **cardiology("pat_001", when=TUESDAY_1030.replace(minute=15)))

    assert refused.value.code == ErrorCode.NOT_A_SLOT
    assert [s["scheduled_for"] for s in refused.value.suggestions][:2] == [
        "2027-01-12T10:00:00+05:30",
        "2027-01-12T10:30:00+05:30",
    ]
    assert await count_bookings(session_factory) == 0


async def test_taken_slot_offers_the_other_free_slot(session_factory):
    await book(session_factory, **cardiology("pat_001"))

    with pytest.raises(ConciergeError) as refused:
        await book(session_factory, **cardiology("pat_002"))

    assert refused.value.suggestions[0]["scheduled_for"] == "2027-01-12T10:00:00+05:30"


async def test_service_not_offered_at_the_patients_society(session_factory):
    # pat_010 lives at Lotus Tower, where physiotherapy is not offered.
    with pytest.raises(ConciergeError) as refused:
        await book(
            session_factory,
            patient_id="pat_010",
            service=Service.DOCTOR,
            subtype="PHYSIOTHERAPY",
            scheduled_for=datetime(2027, 1, 12, 17, 0, tzinfo=IST),
            request_id=uuid.uuid4(),
        )

    assert refused.value.code == ErrorCode.NOT_OFFERED_AT_SOCIETY
    assert "Lotus Tower" in refused.value.message


async def test_unknown_subtype_is_refused(session_factory):
    with pytest.raises(ConciergeError) as refused:
        await book(session_factory, **{**cardiology("pat_001"), "subtype": "NEUROLOGY"})

    assert refused.value.code == ErrorCode.UNKNOWN_SUBTYPE


async def test_cancelled_booking_frees_the_slot(session_factory):
    await book(session_factory, **cardiology("pat_001"))
    async with session_factory() as session, session.begin():
        await session.execute(update(ServiceRequest).values(status="CANCELLED"))

    booking = await book(session_factory, **cardiology("pat_002"))

    assert booking["patient_id"] == "pat_002"


# ---------- free slots ----------

from app.booking import available_slots  # noqa: E402

MONDAY_NOON = datetime(2027, 1, 11, 12, 0, tzinfo=IST)


async def slots_for(session_factory, patient_id="pat_001", subtype="CARDIOLOGY", service=Service.DOCTOR, **kwargs):
    return await available_slots(
        session_factory, patient_id=patient_id, service=service, subtype=subtype, now=MONDAY_NOON, **kwargs
    )


async def test_free_slots_are_the_patients_societys_grid_soonest_first(session_factory):
    shivalik = await slots_for(session_factory)  # Dr. Khanna, Tuesdays 10:00 and 10:30
    lotus = await slots_for(session_factory, patient_id="pat_010")  # Dr. Kapoor, Wednesdays 11:00 and 11:30

    assert [s["scheduled_for"] for s in shivalik][:3] == [
        "2027-01-12T10:00:00+05:30",
        "2027-01-12T10:30:00+05:30",
        "2027-01-19T10:00:00+05:30",
    ]
    assert {s["clinician_name"] for s in shivalik} == {"Dr. Arvind Khanna"}
    assert lotus[0]["scheduled_for"] == "2027-01-13T11:00:00+05:30"
    assert {s["clinician_name"] for s in lotus} == {"Dr. Neha Kapoor"}


async def test_a_booked_slot_is_not_offered(session_factory):
    await book(session_factory, **cardiology("pat_002"))  # takes Tuesday 10:30

    slots = await slots_for(session_factory)

    assert "2027-01-12T10:30:00+05:30" not in [s["scheduled_for"] for s in slots]
    assert slots[0]["scheduled_for"] == "2027-01-12T10:00:00+05:30"


async def test_slots_in_the_past_are_not_offered(session_factory):
    after_the_first_slot = datetime(2027, 1, 12, 10, 5, tzinfo=IST)

    slots = await available_slots(
        session_factory, patient_id="pat_001", service=Service.DOCTOR, subtype="CARDIOLOGY", now=after_the_first_slot
    )

    assert slots[0]["scheduled_for"] == "2027-01-12T10:30:00+05:30"


async def test_free_slots_can_start_from_a_later_day(session_factory):
    slots = await slots_for(session_factory, start=date(2027, 1, 18))

    assert slots[0]["scheduled_for"] == "2027-01-19T10:00:00+05:30"


async def test_free_slots_for_something_not_offered_is_refused(session_factory):
    with pytest.raises(ConciergeError) as refused:
        await slots_for(session_factory, patient_id="pat_010", subtype="PHYSIOTHERAPY")

    assert refused.value.code == ErrorCode.NOT_OFFERED_AT_SOCIETY


# ---------- the patient asks again for a slot they already hold ----------


async def test_same_patient_same_slot_new_request_is_told_it_is_already_theirs(session_factory):
    first = await book(session_factory, **cardiology("pat_001"))

    again = await book(session_factory, **cardiology("pat_001"))  # a new request_id: a retyped message

    assert again["id"] == first["id"]
    assert again["already_booked"] is True
    assert "already_booked" not in first
    assert await count_bookings(session_factory) == 1


async def test_another_patient_is_still_told_the_slot_is_taken_and_learns_nothing_else(session_factory):
    await book(session_factory, **cardiology("pat_001"))

    with pytest.raises(ConciergeError) as refused:
        await book(session_factory, **cardiology("pat_002"))

    assert refused.value.code == ErrorCode.SLOT_TAKEN
    assert "pat_001" not in refused.value.message and "Ananya" not in refused.value.message


async def test_a_cancelled_booking_of_ones_own_does_not_count_as_already_booked(session_factory):
    first = await book(session_factory, **cardiology("pat_001"))
    async with session_factory() as session, session.begin():
        await session.execute(update(ServiceRequest).values(status="CANCELLED"))

    again = await book(session_factory, **cardiology("pat_001"))

    assert again["id"] != first["id"] and "already_booked" not in again
