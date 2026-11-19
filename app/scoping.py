"""Society scoping lives here and nowhere else.

Every function that reads bookings or documents for a patient is in this
module and takes `society_id` as a required keyword argument, which goes
straight into the SQL WHERE clause. No other module reads those tables on a
patient's behalf.

The caller gets `society_id` from the patient's own row via `get_patient`,
never from the model or the request body.
"""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Select, cast, literal, or_, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.contract import Service
from app.db.models import Clinician, DocChunk, Document, Patient, ServiceRequest, Society


async def get_patient(session: AsyncSession, patient_id: str) -> Patient | None:
    """The one unscoped read: this is how we learn which society a patient is in."""
    return await session.get(Patient, patient_id)


def booking_to_dict(row: ServiceRequest, clinician_name: str, timezone: str) -> dict:
    """The shape every booking is reported in. Time is shown in the society's timezone."""
    return {
        "id": str(row.id),
        "patient_id": row.patient_id,
        "society_id": row.society_id,
        "clinician_id": row.clinician_id,
        "clinician_name": clinician_name,
        "service": row.service,
        "subtype": row.subtype,
        "scheduled_for": row.scheduled_for.astimezone(ZoneInfo(timezone)).isoformat(),
        "status": row.status,
        "request_id": str(row.request_id),
    }


def _bookings(society_id: str) -> Select:
    """Base query for every booking read. The society filter is not optional."""
    return (
        select(ServiceRequest, Clinician.name, Society.timezone)
        .join(Clinician, Clinician.id == ServiceRequest.clinician_id)
        .join(Society, Society.id == ServiceRequest.society_id)
        .where(ServiceRequest.society_id == society_id)
    )


async def list_bookings(
    session: AsyncSession, *, society_id: str, patient_id: str, status: str | None = None
) -> list[dict]:
    query = _bookings(society_id).where(ServiceRequest.patient_id == patient_id)
    if status is not None:
        query = query.where(ServiceRequest.status == status)
    rows = await session.execute(query.order_by(ServiceRequest.scheduled_for))
    return [booking_to_dict(*row) for row in rows]


async def find_booking_by_request_id(
    session: AsyncSession, *, society_id: str, patient_id: str, request_id: uuid.UUID
) -> dict | None:
    """Used to recognise a repeated request. Scoped to the patient, so one
    patient can never be handed another patient's booking."""
    query = _bookings(society_id).where(
        ServiceRequest.patient_id == patient_id, ServiceRequest.request_id == request_id
    )
    row = (await session.execute(query)).first()
    return booking_to_dict(*row) if row else None


async def find_own_active_booking(
    session: AsyncSession, *, society_id: str, patient_id: str, clinician_id: str, scheduled_for: datetime
) -> dict | None:
    """This patient's own active booking in a slot, if they hold it. Scoped to the
    patient, so it can never reveal who else has the slot."""
    query = _bookings(society_id).where(
        ServiceRequest.patient_id == patient_id,
        ServiceRequest.clinician_id == clinician_id,
        ServiceRequest.scheduled_for == scheduled_for,
        ServiceRequest.status == "BOOKED",
    )
    row = (await session.execute(query)).first()
    return booking_to_dict(*row) if row else None


async def booked_times(
    session: AsyncSession, *, society_id: str, clinician_id: str, start: datetime, end: datetime
) -> set[datetime]:
    """Slot starts already taken for a clinician at this society. Returns times only."""
    query = select(ServiceRequest.scheduled_for).where(
        ServiceRequest.society_id == society_id,
        ServiceRequest.clinician_id == clinician_id,
        ServiceRequest.status == "BOOKED",
        ServiceRequest.scheduled_for >= start,
        ServiceRequest.scheduled_for < end,
    )
    return set((await session.scalars(query)).all())


async def clinicians_offering(
    session: AsyncSession, *, society_id: str, service: Service, subtype: str
) -> list[Clinician]:
    """Clinicians who do this service and subtype AND visit this society."""
    visits_society = Clinician.availability.contains(cast([{"society_id": society_id}], JSONB))
    query = (
        select(Clinician)
        .where(
            Clinician.service == service.value,
            Clinician.subtypes.any(subtype),
            visits_society,
        )
        .order_by(Clinician.id)
    )
    return list((await session.scalars(query)).all())


def chunk_search_query(*, society_id: str, query_embedding: list[float], k: int) -> Select:
    """Dense search only: nearest chunks by cosine distance, among the chunks this society may see.

    Both filters are in the WHERE clause, so Postgres applies them BEFORE it
    ranks and cuts to k. Filtering the top k afterwards in Python would be
    wrong twice over: another society's text would have been read, and the
    patient's own answer could have been pushed out of the top k.
    """
    distance = DocChunk.embedding.cosine_distance(query_embedding)  # pgvector's <=> operator
    return (
        select(
            DocChunk.heading_path,
            DocChunk.content,
            Document.doc_id,
            Document.version,
            Document.title,
            Document.society_id,
            (1 - distance).label("similarity"),
            literal(False).label("keyword_match"),
        )
        .join(Document, Document.id == DocChunk.document_id)
        .where(
            # the current version only: superseded documents are stored but never searched
            Document.is_current.is_(True),
            # the patient's own society, plus documents shared by all societies (NULL)
            or_(Document.society_id == society_id, Document.society_id.is_(None)),
        )
        .order_by(distance)
        .limit(k)
    )


# The usual constant for reciprocal rank fusion. It flattens the gap between rank 1 and
# rank 2, so a chunk ranked well by both searches beats one ranked first by only one.
RRF_K = 60

# Dense search and keyword search, merged with reciprocal rank fusion (RRF).
#
#   visible  the only chunks this patient may see. The society and version filters are
#            here, in its WHERE clause, and every later step reads only from `visible`.
#   dense    the nearest chunks by embedding: good at meaning and at other languages.
#   keyword  chunks sharing words with the question: good at exact terms such as "CBC"
#            or a fact in a table row. A word found in few chunks counts for more than
#            a word found in many, so "CBC" outweighs "time".
#   result   a chunk scores 1/(60 + its rank) in each list it appears in, added up.
HYBRID_SEARCH_SQL = text(
    """
    WITH visible AS (
        SELECT c.id, c.embedding, c.search_text
        FROM doc_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.is_current IS TRUE
          AND (d.society_id = :society_id OR d.society_id IS NULL)
    ),
    dense AS (
        SELECT id, row_number() OVER (ORDER BY embedding <=> CAST(:embedding AS vector)) AS rank
        FROM visible
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :candidates
    ),
    terms AS (
        -- the question's words, stemmed, without stop words
        SELECT unnest(tsvector_to_array(to_tsvector('english', :query_text))) AS term
    ),
    term_weight AS (
        SELECT t.term, ln(1 + (SELECT count(*) FROM visible)::float / count(*)) AS weight
        FROM terms t
        JOIN visible v ON v.search_text @@ plainto_tsquery('simple', t.term)
        GROUP BY t.term
    ),
    keyword_score AS (
        -- rounded, so two chunks matching the same words score exactly the same and the
        -- tie is broken by id below; unrounded, the order of a floating-point sum could
        -- differ between two databases and reorder the results
        SELECT v.id, round(sum(w.weight)::numeric, 6) AS score
        FROM visible v
        JOIN term_weight w ON v.search_text @@ plainto_tsquery('simple', w.term)
        GROUP BY v.id
    ),
    keyword AS (
        SELECT id, row_number() OVER (ORDER BY score DESC, id) AS rank
        FROM keyword_score
        ORDER BY score DESC, id
        LIMIT :candidates
    )
    SELECT c.heading_path, c.content, d.doc_id, d.version, d.title, d.society_id,
           1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity,
           keyword.rank IS NOT NULL AS keyword_match
    FROM dense
    FULL OUTER JOIN keyword ON keyword.id = dense.id
    JOIN doc_chunks c ON c.id = COALESCE(dense.id, keyword.id)
    JOIN documents d ON d.id = c.document_id
    ORDER BY COALESCE(1.0 / (:rrf_k + dense.rank), 0) + COALESCE(1.0 / (:rrf_k + keyword.rank), 0) DESC,
             similarity DESC,
             c.id
    LIMIT :k
    """
)


async def search_chunks(
    session: AsyncSession,
    *,
    society_id: str,
    query_embedding: list[float],
    k: int,
    query_text: str | None = None,
) -> list[dict]:
    """Search this society's current documents. With `query_text` it is a hybrid
    search; without it, dense only."""
    if query_text:
        rows = await session.execute(
            HYBRID_SEARCH_SQL,
            {
                "society_id": society_id,
                "embedding": str(query_embedding),  # pgvector reads '[0.1, 0.2, ...]'
                "query_text": query_text,
                # Each search contributes its own top k. Longer lists were tried (8, 10, 20)
                # and did worse: with only ~47 chunks visible, a long list holds almost
                # everything, so "appears in both lists" stops meaning anything.
                "candidates": k,
                "rrf_k": RRF_K,
                "k": k,
            },
        )
    else:
        rows = await session.execute(
            chunk_search_query(society_id=society_id, query_embedding=query_embedding, k=k)
        )
    return [
        {
            "doc_id": row.doc_id,
            "version": row.version,
            "title": row.title,
            "society_id": row.society_id,
            "heading_path": row.heading_path,
            "content": row.content,
            "similarity": round(float(row.similarity), 4),
            "keyword_match": bool(row.keyword_match),
        }
        for row in rows
    ]
