"""Alembic entry point: connects to the database and runs the migration files."""

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.db.models import Base

# Lets `alembic check` compare the models against the migrated database.
target_metadata = Base.metadata


def run_migrations() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
