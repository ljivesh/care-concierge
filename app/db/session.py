"""Engine and session factory.

Nothing is created at import time. The app builds one engine at startup and
passes the session factory to whatever needs it; tests build their own.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings


def make_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        # Postgres itself cancels any statement that runs longer than this,
        # so every database call has a timeout without wrapping each one.
        connect_args={"options": f"-c statement_timeout={settings.db_statement_timeout_ms}"},
        pool_pre_ping=True,
    )


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: objects stay readable after commit without a re-query.
    return async_sessionmaker(engine, expire_on_commit=False)
