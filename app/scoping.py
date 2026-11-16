"""Society scoping lives here and nowhere else.

Every function that reads bookings (and, later, documents) is in this module
and takes `society_id` as a required keyword argument, which goes straight
into the SQL WHERE clause. No other module queries those tables for reading.

The caller gets `society_id` from the patient's own row via `get_patient`,
never from the model or the request body.
"""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Select, cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.contract import Service
from app.db.models import Clinician, Patient, ServiceRequest, Society


async def get_patient(session: AsyncSession, patient_id: str) -> Patient | None:
    """The one unscoped read: this is how we learn which society a patient is in."""
    return await session.get(Patient, patient_id)


def booking_to_dict(row: ServiceRequest, clinician_name: str, timezone: str) -> dict:
    """The shape every booking is reported in. Time is shown in the society's timezone."""
    return {
        "id": str(row.id),
        "patient_id": row.patient_id,
        "society_id": row.society_id,
        "clinician_id": row.clinician_id,
        "clinician_name": clinician_name,
        "service": row.service,
        "subtype": row.subtype,
        "scheduled_for": row.scheduled_for.astimezone(ZoneInfo(timezone)).isoformat(),
        "status": row.status,
        "request_id": str(row.request_id),
    }


def _bookings(society_id: str) -> Select:
    """Base query for every booking read. The society filter is not optional."""
    return (
        select(ServiceRequest, Clinician.name, Society.timezone)
        .join(Clinician, Clinician.id == ServiceRequest.clinician_id)
        .join(Society, Society.id == ServiceRequest.society_id)
        .where(ServiceRequest.society_id == society_id)
    )


async def list_bookings(
    session: AsyncSession, *, society_id: str, patient_id: str, status: str | None = None
) -> list[dict]:
    query = _bookings(society_id).where(ServiceRequest.patient_id == patient_id)
    if status is not None:
        query = query.where(ServiceRequest.status == status)
    rows = await session.execute(query.order_by(ServiceRequest.scheduled_for))
    return [booking_to_dict(*row) for row in rows]


async def find_booking_by_request_id(
    session: AsyncSession, *, society_id: str, patient_id: str, request_id: uuid.UUID
) -> dict | None:
    """Used to recognise a repeated request. Scoped to the patient, so one
    patient can never be handed another patient's booking."""
    query = _bookings(society_id).where(
        ServiceRequest.patient_id == patient_id, ServiceRequest.request_id == request_id
    )
    row = (await session.execute(query)).first()
    return booking_to_dict(*row) if row else None


async def booked_times(
    session: AsyncSession, *, society_id: str, clinician_id: str, start: datetime, end: datetime
) -> set[datetime]:
    """Slot starts already taken for a clinician at this society. Returns times only."""
    query = select(ServiceRequest.scheduled_for).where(
        ServiceRequest.society_id == society_id,
        ServiceRequest.clinician_id == clinician_id,
        ServiceRequest.status == "BOOKED",
        ServiceRequest.scheduled_for >= start,
        ServiceRequest.scheduled_for < end,
    )
    return set((await session.scalars(query)).all())


async def clinicians_offering(
    session: AsyncSession, *, society_id: str, service: Service, subtype: str
) -> list[Clinician]:
    """Clinicians who do this service and subtype AND visit this society."""
    visits_society = Clinician.availability.contains(cast([{"society_id": society_id}], JSONB))
    query = (
        select(Clinician)
        .where(
            Clinician.service == service.value,
            Clinician.subtypes.any(subtype),
            visits_society,
        )
        .order_by(Clinician.id)
    )
    return list((await session.scalars(query)).all())
