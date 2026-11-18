"""The eight tables, as SQLAlchemy 2.x models.

The migration in migrations/versions/ is what actually builds the database;
these classes describe the same tables to Python. `alembic check` fails if the
two ever drift apart.

Constraint names are chosen on purpose: when Postgres rejects a write, the
error carries the constraint name, and app code turns that name into a clear
sentence for the patient.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Constraint names referenced by the error-translation code.
UQ_ACTIVE_SLOT = "uq_service_requests_active_clinician_slot"
UQ_SERVICE_REQUEST_ID = "uq_service_requests_request_id"
UQ_SYMPTOM_REQUEST_ID = "uq_symptom_logs_request_id"
UQ_ESCALATION_REQUEST_ID = "uq_escalations_request_id"
CK_SEVERITY = "ck_symptom_logs_severity_1_to_5"

EMBEDDING_DIM = 768  # must match app/embeddings.py and migration 0002


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    # The database generates the id, so rows inserted by any client get one.
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Society(Base):
    __tablename__ = "societies"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # e.g. "soc_lotus"
    name: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text)  # IANA name, e.g. "Asia/Kolkata"
    annex_doc_id: Mapped[str] = mapped_column(Text)
    # The partner hospital is folded in; there is no hospitals table.
    hospital_name: Mapped[str] = mapped_column(Text)
    hospital_address: Mapped[str] = mapped_column(Text)
    hospital_front_desk_phone: Mapped[str] = mapped_column(Text)
    hospital_emergency_phone: Mapped[str] = mapped_column(Text)


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint("language IN ('en', 'hi', 'hinglish')", name="ck_patients_language"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # e.g. "pat_001"
    society_id: Mapped[str] = mapped_column(ForeignKey("societies.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text, unique=True)
    language: Mapped[str] = mapped_column(Text)
    date_of_birth: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(Text)
    flat: Mapped[str] = mapped_column(Text)


class Clinician(Base):
    __tablename__ = "clinicians"
    __table_args__ = (
        CheckConstraint("service IN ('DOCTOR', 'LAB')", name="ck_clinicians_service"),
        CheckConstraint("slot_minutes > 0", name="ck_clinicians_slot_minutes_positive"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # e.g. "cln_02"
    name: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    service: Mapped[str] = mapped_column(Text)
    subtypes: Mapped[list[str]] = mapped_column(ARRAY(Text))  # codes from the department directory
    hospital: Mapped[str] = mapped_column(Text)
    slot_minutes: Mapped[int] = mapped_column(Integer)
    # Weekly windows: [{"society_id", "weekday", "start", "end"}, ...].
    # Kept as JSON because the contract fixes the table count at eight.
    availability: Mapped[list[dict]] = mapped_column(JSONB)


class ServiceRequest(Base):
    """A booking: one patient, one clinician, one slot start."""

    __tablename__ = "service_requests"
    __table_args__ = (
        CheckConstraint("service IN ('DOCTOR', 'LAB')", name="ck_service_requests_service"),
        CheckConstraint(
            "status IN ('BOOKED', 'CANCELLED', 'COMPLETED', 'NO_SHOW')",
            name="ck_service_requests_status",
        ),
        # Rule 1: a repeated request writes once.
        UniqueConstraint("request_id", name=UQ_SERVICE_REQUEST_ID),
        # Rule 2: one clinician cannot hold two ACTIVE bookings for one slot.
        # Partial, so a cancelled booking frees the slot for someone else.
        # No society_id here on purpose: a clinician has a single calendar.
        Index(
            UQ_ACTIVE_SLOT,
            "clinician_id",
            "scheduled_for",
            unique=True,
            postgresql_where=text("status = 'BOOKED'"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    society_id: Mapped[str] = mapped_column(ForeignKey("societies.id"), index=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("clinicians.id"))
    service: Mapped[str] = mapped_column(Text)
    subtype: Mapped[str] = mapped_column(Text)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, server_default=text("'BOOKED'"))
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created_at()


class SymptomLog(Base):
    __tablename__ = "symptom_logs"
    __table_args__ = (
        # Rule 3: severity is 1 to 5, enforced by the database.
        CheckConstraint("severity BETWEEN 1 AND 5", name=CK_SEVERITY),
        UniqueConstraint("request_id", name=UQ_SYMPTOM_REQUEST_ID),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    symptom: Mapped[str] = mapped_column(Text)
    severity: Mapped[int] = mapped_column(SmallInteger)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created_at()


class Escalation(Base):
    """Fields follow 'What every escalation records' in the escalation SLA document."""

    __tablename__ = "escalations"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 3", name="ck_escalations_level_1_to_3"),
        CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED', 'CLOSED')", name="ck_escalations_status"
        ),
        UniqueConstraint("request_id", name=UQ_ESCALATION_REQUEST_ID),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    society_id: Mapped[str] = mapped_column(ForeignKey("societies.id"), index=True)
    level: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(Text, server_default=text("'OPEN'"))
    transcript: Mapped[str] = mapped_column(Text)
    response_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(Text)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created_at()


class Document(Base):
    """One row per corpus file. Two versions of a policy share a doc_id."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("doc_id", "version", name="uq_documents_doc_id_version"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    doc_id: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    # NULL means "applies to all societies"; otherwise the one society it belongs to.
    society_id: Mapped[str | None] = mapped_column(ForeignKey("societies.id"), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    superseded_by: Mapped[str | None] = mapped_column(Text)
    # False once a newer version replaced it; search only reads current rows.
    is_current: Mapped[bool] = mapped_column()
    source_path: Mapped[str] = mapped_column(Text)
    # Hash of the file, so ingestion can tell when nothing changed and skip re-embedding.
    source_sha256: Mapped[str] = mapped_column(Text)


class DocChunk(Base):
    """One heading-level section of a document, with its embedding."""

    __tablename__ = "doc_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_doc_chunks_document_chunk"),
        Index("ix_doc_chunks_search_text", "search_text", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    heading_path: Mapped[str] = mapped_column(Text)  # "Title > Section > Subsection"
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    # For keyword search. Computed by Postgres from the heading and the text.
    search_text: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', heading_path || ' ' || content)", persisted=True)
    )
