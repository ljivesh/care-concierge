"""The LangGraph checkpointer, stored in the same Postgres as everything else.

It is the transcript store: there is no conversations or messages table.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine import make_url

from app.config import Settings


def _conninfo(database_url: str) -> str:
    """SQLAlchemy writes postgresql+psycopg://...; psycopg itself wants postgresql://..."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


@asynccontextmanager
async def open_checkpointer(settings: Settings) -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncConnectionPool(
        _conninfo(settings.database_url),
        # These three settings are what the LangGraph saver requires of its connections.
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        max_size=10,
        open=False,
    ) as pool:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()  # creates the checkpoint tables if they are missing
        yield saver
