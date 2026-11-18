"""pgvector: an embedding on every chunk, and a content hash on every document.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0002"
down_revision = "0001"

EMBEDDING_DIM = 768  # paraphrase-multilingual-mpnet-base-v2


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Both tables are still empty here (ingestion needs these columns), so NOT NULL is safe.
    op.add_column("doc_chunks", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False))
    op.add_column("documents", sa.Column("source_sha256", sa.Text, nullable=False))
    # No vector index, deliberately. With about 80 chunks an exact scan is instant,
    # and an approximate index (HNSW/IVFFlat) picks its nearest rows BEFORE the
    # WHERE filters apply, so a society filter could silently drop results.


def downgrade() -> None:
    op.drop_column("documents", "source_sha256")
    op.drop_column("doc_chunks", "embedding")
