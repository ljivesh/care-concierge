"""Keyword search on chunks: a tsvector column kept up to date by Postgres, with a GIN index.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    # A generated column: Postgres computes it from the heading and the text on
    # every insert or update, so ingestion does not have to know it exists.
    # 'english' stems words, so "fasting" matches "fast" and "covered" matches "cover".
    op.add_column(
        "doc_chunks",
        sa.Column(
            "search_text",
            postgresql.TSVECTOR,
            sa.Computed("to_tsvector('english', heading_path || ' ' || content)", persisted=True),
        ),
    )
    op.create_index("ix_doc_chunks_search_text", "doc_chunks", ["search_text"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_doc_chunks_search_text", table_name="doc_chunks")
    op.drop_column("doc_chunks", "search_text")
