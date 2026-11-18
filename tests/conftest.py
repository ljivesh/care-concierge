"""Test setup: a separate, real Postgres database, built by the real migration.

Every test run drops and recreates `<dbname>_test`, runs `alembic upgrade head`
on it (so the migration is proven on an empty database each time), seeds it and
ingests the corpus.
"""

import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings

ROOT = Path(__file__).resolve().parent.parent

_main_url = make_url(Settings().database_url)
TEST_DB = f"{_main_url.database}_test"

# Point the whole app at the test database before anything reads the settings.
os.environ["DATABASE_URL"] = _main_url.set(database=TEST_DB).render_as_string(hide_password=False)
get_settings.cache_clear()

from app.db.session import make_engine, make_session_factory  # noqa: E402
from app.embeddings import Embedder  # noqa: E402
from app.ingest import ingest  # noqa: E402
from app.seed import main as seed_main  # noqa: E402


@pytest.fixture(scope="session")
def embedder() -> Embedder:
    """The real local model, loaded once for the whole run."""
    return Embedder()


async def _ingest_corpus(embedder: Embedder) -> None:
    engine = make_engine(get_settings())
    try:
        await ingest(make_session_factory(engine), embedder)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _test_database(embedder):
    admin = create_engine(_main_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()

    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    asyncio.run(seed_main())
    asyncio.run(_ingest_corpus(embedder))


@pytest.fixture
async def session_factory():
    """A fresh engine per test, with the tables that tests write to emptied."""
    assert get_settings().database_url.endswith("_test"), "refusing to truncate a non-test database"
    engine = make_engine(get_settings())
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE service_requests, symptom_logs, escalations"))
    yield make_session_factory(engine)
    await engine.dispose()
