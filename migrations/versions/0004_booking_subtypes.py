"""A booking is one visit that can carry several tests: subtype becomes subtypes.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    # Three steps, so existing bookings keep their test: add the column empty,
    # copy each row's single subtype into it, then make it required.
    op.add_column("service_requests", sa.Column("subtypes", postgresql.ARRAY(sa.Text), nullable=True))
    op.execute("UPDATE service_requests SET subtypes = ARRAY[subtype]")
    op.alter_column("service_requests", "subtypes", nullable=False)
    op.drop_column("service_requests", "subtype")


def downgrade() -> None:
    op.add_column("service_requests", sa.Column("subtype", sa.Text, nullable=True))
    op.execute("UPDATE service_requests SET subtype = subtypes[1]")  # Postgres arrays start at 1
    op.alter_column("service_requests", "subtype", nullable=False)
    op.drop_column("service_requests", "subtypes")
