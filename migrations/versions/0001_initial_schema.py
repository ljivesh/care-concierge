"""Initial schema: the eight tables and the three database-enforced rules.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMPTZ = sa.DateTime(timezone=True)


def _uuid_pk() -> sa.Column:
    return sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _created_at() -> sa.Column:
    return sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "societies",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("city", sa.Text, nullable=False),
        sa.Column("address", sa.Text, nullable=False),
        sa.Column("timezone", sa.Text, nullable=False),
        sa.Column("annex_doc_id", sa.Text, nullable=False),
        sa.Column("hospital_name", sa.Text, nullable=False),
        sa.Column("hospital_address", sa.Text, nullable=False),
        sa.Column("hospital_front_desk_phone", sa.Text, nullable=False),
        sa.Column("hospital_emergency_phone", sa.Text, nullable=False),
    )

    op.create_table(
        "patients",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("society_id", sa.Text, sa.ForeignKey("societies.id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("phone", sa.Text, nullable=False, unique=True),
        sa.Column("language", sa.Text, nullable=False),
        sa.Column("date_of_birth", sa.Date, nullable=False),
        sa.Column("gender", sa.Text, nullable=False),
        sa.Column("flat", sa.Text, nullable=False),
        sa.CheckConstraint("language IN ('en', 'hi', 'hinglish')", name="ck_patients_language"),
    )
    op.create_index("ix_patients_society_id", "patients", ["society_id"])

    op.create_table(
        "clinicians",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("service", sa.Text, nullable=False),
        sa.Column("subtypes", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column("hospital", sa.Text, nullable=False),
        sa.Column("slot_minutes", sa.Integer, nullable=False),
        sa.Column("availability", postgresql.JSONB, nullable=False),
        sa.CheckConstraint("service IN ('DOCTOR', 'LAB')", name="ck_clinicians_service"),
        sa.CheckConstraint("slot_minutes > 0", name="ck_clinicians_slot_minutes_positive"),
    )

    op.create_table(
        "service_requests",
        _uuid_pk(),
        sa.Column("patient_id", sa.Text, sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("society_id", sa.Text, sa.ForeignKey("societies.id"), nullable=False),
        sa.Column("clinician_id", sa.Text, sa.ForeignKey("clinicians.id"), nullable=False),
        sa.Column("service", sa.Text, nullable=False),
        sa.Column("subtype", sa.Text, nullable=False),
        sa.Column("scheduled_for", TIMESTAMPTZ, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'BOOKED'")),
        sa.Column("request_id", UUID, nullable=False),
        _created_at(),
        sa.CheckConstraint("service IN ('DOCTOR', 'LAB')", name="ck_service_requests_service"),
        sa.CheckConstraint(
            "status IN ('BOOKED', 'CANCELLED', 'COMPLETED', 'NO_SHOW')",
            name="ck_service_requests_status",
        ),
        # Rule: a repeated request writes once.
        sa.UniqueConstraint("request_id", name="uq_service_requests_request_id"),
    )
    op.create_index("ix_service_requests_patient_id", "service_requests", ["patient_id"])
    op.create_index("ix_service_requests_society_id", "service_requests", ["society_id"])
    # Rule: one clinician cannot hold two active bookings for the same slot.
    # Partial unique index: only rows with status BOOKED take part, so a
    # cancelled booking does not block the slot.
    op.create_index(
        "uq_service_requests_active_clinician_slot",
        "service_requests",
        ["clinician_id", "scheduled_for"],
        unique=True,
        postgresql_where=sa.text("status = 'BOOKED'"),
    )

    op.create_table(
        "symptom_logs",
        _uuid_pk(),
        sa.Column("patient_id", sa.Text, sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("symptom", sa.Text, nullable=False),
        sa.Column("severity", sa.SmallInteger, nullable=False),
        sa.Column("request_id", UUID, nullable=False),
        _created_at(),
        # Rule: severity is 1 to 5.
        sa.CheckConstraint("severity BETWEEN 1 AND 5", name="ck_symptom_logs_severity_1_to_5"),
        sa.UniqueConstraint("request_id", name="uq_symptom_logs_request_id"),
    )
    op.create_index("ix_symptom_logs_patient_id", "symptom_logs", ["patient_id"])

    op.create_table(
        "escalations",
        _uuid_pk(),
        sa.Column("patient_id", sa.Text, sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("society_id", sa.Text, sa.ForeignKey("societies.id"), nullable=False),
        sa.Column("level", sa.SmallInteger, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'OPEN'")),
        sa.Column("transcript", sa.Text, nullable=False),
        sa.Column("response_due_at", TIMESTAMPTZ, nullable=False),
        sa.Column("acknowledged_by", sa.Text),
        sa.Column("acknowledged_at", TIMESTAMPTZ),
        sa.Column("closed_at", TIMESTAMPTZ),
        sa.Column("resolution", sa.Text),
        sa.Column("request_id", UUID, nullable=False),
        _created_at(),
        sa.CheckConstraint("level BETWEEN 1 AND 3", name="ck_escalations_level_1_to_3"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED', 'CLOSED')", name="ck_escalations_status"
        ),
        sa.UniqueConstraint("request_id", name="uq_escalations_request_id"),
    )
    op.create_index("ix_escalations_patient_id", "escalations", ["patient_id"])
    op.create_index("ix_escalations_society_id", "escalations", ["society_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("doc_id", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        # NULL = shared by all societies.
        sa.Column("society_id", sa.Text, sa.ForeignKey("societies.id")),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("superseded_by", sa.Text),
        sa.Column("is_current", sa.Boolean, nullable=False),
        sa.Column("source_path", sa.Text, nullable=False),
        sa.UniqueConstraint("doc_id", "version", name="uq_documents_doc_id_version"),
    )
    op.create_index("ix_documents_society_id", "documents", ["society_id"])

    op.create_table(
        "doc_chunks",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("heading_path", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_doc_chunks_document_chunk"),
    )


def downgrade() -> None:
    for table in (
        "doc_chunks",
        "documents",
        "escalations",
        "symptom_logs",
        "service_requests",
        "clinicians",
        "patients",
        "societies",
    ):
        op.drop_table(table)
