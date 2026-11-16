"""Load data/seed/*.json into societies, clinicians and patients.

Run with:  python -m app.seed
Safe to run again: each row is an upsert on its id, so nothing is duplicated.
"""

import asyncio
import json
from datetime import date
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Base, Clinician, Patient, Society
from app.db.session import make_engine, make_session_factory

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


def _load(name: str) -> list[dict]:
    return json.loads((SEED_DIR / name).read_text(encoding="utf-8"))


async def _upsert(session: AsyncSession, model: type[Base], rows: list[dict]) -> None:
    """INSERT ... ON CONFLICT (id) DO UPDATE, one statement for all rows."""
    stmt = insert(model).values(rows)
    updatable = {col: stmt.excluded[col] for col in rows[0] if col != "id"}
    await session.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=updatable))


def _society_row(raw: dict) -> dict:
    hospital = raw["hospital"]
    return {
        "id": raw["id"],
        "name": raw["name"],
        "city": raw["city"],
        "address": raw["address"],
        "timezone": raw["timezone"],
        "annex_doc_id": raw["annex_doc_id"],
        "hospital_name": hospital["name"],
        "hospital_address": hospital["address"],
        "hospital_front_desk_phone": hospital["front_desk_phone"],
        "hospital_emergency_phone": hospital["emergency_phone"],
    }


def _patient_row(raw: dict) -> dict:
    return {**raw, "date_of_birth": date.fromisoformat(raw["date_of_birth"])}


async def seed(session: AsyncSession) -> dict[str, int]:
    societies = [_society_row(r) for r in _load("societies.json")]
    clinicians = _load("clinicians.json")  # JSON keys already match the columns
    patients = [_patient_row(r) for r in _load("patients.json")]

    # Order matters: patients reference societies.
    await _upsert(session, Society, societies)
    await _upsert(session, Clinician, clinicians)
    await _upsert(session, Patient, patients)
    return {"societies": len(societies), "clinicians": len(clinicians), "patients": len(patients)}


async def main() -> None:
    engine = make_engine(get_settings())
    try:
        async with make_session_factory(engine)() as session, session.begin():
            counts = await seed(session)
        print(f"seeded: {counts}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
