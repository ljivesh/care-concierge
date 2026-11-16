"""A patient of one society cannot read another society's bookings."""

import inspect
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from app import scoping
from app.booking import book
from app.contract import Service

IST = ZoneInfo("Asia/Kolkata")


async def test_bookings_are_invisible_from_another_society(session_factory):
    # pat_001 lives at Shivalik Greens.
    request_id = uuid.uuid4()
    await book(
        session_factory,
        patient_id="pat_001",
        service=Service.DOCTOR,
        subtype="CARDIOLOGY",
        scheduled_for=datetime(2027, 1, 12, 10, 30, tzinfo=IST),
        request_id=request_id,
    )

    async with session_factory() as session:
        own = await scoping.list_bookings(session, society_id="soc_shivalik", patient_id="pat_001")
        other = await scoping.list_bookings(session, society_id="soc_lotus", patient_id="pat_001")
        by_request_other = await scoping.find_booking_by_request_id(
            session, society_id="soc_lotus", patient_id="pat_001", request_id=request_id
        )
        slots_other = await scoping.booked_times(
            session,
            society_id="soc_lotus",
            clinician_id="cln_02",
            start=datetime(2027, 1, 1, tzinfo=IST),
            end=datetime(2027, 2, 1, tzinfo=IST),
        )

    assert len(own) == 1
    assert other == []
    assert by_request_other is None
    assert slots_other == set()


async def test_clinician_lookup_is_per_society(session_factory):
    async with session_factory() as session:
        shivalik = await scoping.clinicians_offering(
            session, society_id="soc_shivalik", service=Service.DOCTOR, subtype="CARDIOLOGY"
        )
        lotus = await scoping.clinicians_offering(
            session, society_id="soc_lotus", service=Service.DOCTOR, subtype="CARDIOLOGY"
        )
        royal_ortho = await scoping.clinicians_offering(
            session, society_id="soc_royal", service=Service.DOCTOR, subtype="ORTHOPAEDICS"
        )

    assert [c.id for c in shivalik] == ["cln_02"]  # Dr. Khanna
    assert [c.id for c in lotus] == ["cln_09"]  # Dr. Kapoor
    assert royal_ortho == []  # orthopaedics does not visit Royal Palms


def test_every_scoped_read_requires_society_id():
    """The rule itself: no reader in the scoping module can be called without society_id."""
    unscoped_on_purpose = {"get_patient", "booking_to_dict"}
    for name, fn in inspect.getmembers(scoping, inspect.iscoroutinefunction):
        if name in unscoped_on_purpose or name.startswith("_"):
            continue
        param = inspect.signature(fn).parameters.get("society_id")
        assert param is not None, f"{name} must take society_id"
        assert param.default is inspect.Parameter.empty, f"{name}: society_id must be required"
