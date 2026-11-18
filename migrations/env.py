"""Alembic entry point: connects to the database and runs the migration files."""

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.db.models import Base

# Lets `alembic check` compare the models against the migrated database.
target_metadata = Base.metadata


def only_our_tables(obj, name, type_, reflected, compare_to) -> bool:
    """`alembic check` should compare our eight tables only. The LangGraph
    checkpointer creates and owns its own tables in the same database."""
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table in target_metadata.tables


def run_migrations() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, include_object=only_our_tables
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
