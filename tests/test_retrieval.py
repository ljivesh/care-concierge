"""Chunking, ingestion and search: society-correct, version-correct, and able to say nothing."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from app import scoping
from app.corpus import chunk_by_headings, merge_by_heading, parse_document
from app.db.models import DocChunk, Document
from app.ingest import CORPUS_DIR, ingest
from app.config import get_settings
from app.tools import make_tools, run_tool

SOCIETIES = ["soc_shivalik", "soc_lotus", "soc_royal"]
EVERYTHING = 500  # a k larger than the corpus: returns every chunk the society can see


@pytest.fixture
def tools(session_factory, embedder):
    return make_tools(session_factory, embedder, min_similarity=get_settings().retrieval_min_similarity)


async def search(tools, query: str, society_id: str, k: int = 6) -> list[dict]:
    return await run_tool(
        tools, "search_clinic_docs", {"query": query, "society_id": society_id, "k": k}, timeout_s=30
    )


# ---------- chunking on headings ----------


def test_chunks_follow_headings_and_carry_the_full_path():
    body = "# Title\nintro\n## Section\n### Sub A\ntext a\n### Sub B\ntext b\n## Other\ntext c\n"

    chunks = chunk_by_headings(body)

    assert [(c.heading_path, c.content) for c in chunks] == [
        ("Title", "intro"),
        ("Title > Section > Sub A", "text a"),  # "Section" has no text of its own: no chunk
        ("Title > Section > Sub B", "text b"),
        ("Title > Other", "text c"),
    ]


def test_real_document_front_matter_and_citation_path():
    doc = parse_document((CORPUS_DIR / "annex-lotus-tower.md").read_text(encoding="utf-8"))

    assert (doc.doc_id, doc.version, doc.society_id) == ("annex-lotus-tower", 3, "soc_lotus")
    hours = [c for c in doc.chunks if c.heading_path.endswith("Hours")]
    # The exact path the bundle README gives as an example citation.
    assert {c.heading_path for c in hours} == {"Society Annex — Lotus Tower > Wellness room > Hours"}
    # One chunk for the section's sentence, then one per table row, each with the header.
    assert hours[0].content == "Wellness room phone: +91 120 4555 3301."
    assert "| Day | Hours |\n|---|---|\n| Sunday | Closed |" in [c.content for c in hours]
    assert len(hours) == 5


def test_each_table_row_is_its_own_chunk_with_the_header():
    body = "# T\n## Tests\nintro\n\n| Code | Report in |\n|---|---|\n| CBC | 6 hours |\n| LFT | 24 hours |\n\noutro\n"

    chunks = chunk_by_headings(body)

    assert [(c.heading_path, c.content) for c in chunks] == [
        ("T > Tests", "intro\n\n\noutro"),
        ("T > Tests", "| Code | Report in |\n|---|---|\n| CBC | 6 hours |"),
        ("T > Tests", "| Code | Report in |\n|---|---|\n| LFT | 24 hours |"),
    ]


def test_chunks_under_one_heading_merge_into_one_passage():
    def chunk(heading, content, similarity, keyword=False, doc="d"):
        return {"doc_id": doc, "version": 1, "heading_path": heading, "content": content, "similarity": similarity, "keyword_match": keyword}

    merged = merge_by_heading(
        [
            chunk("T > Tests", "| Code | Report in |\n|---|---|\n| CBC | 6 hours |", 0.3, keyword=True),
            chunk("T > Other", "something else", 0.5),
            chunk("T > Tests", "| Code | Report in |\n|---|---|\n| LFT | 24 hours |", 0.6),
        ]
    )

    assert [p["heading_path"] for p in merged] == ["T > Tests", "T > Other"]  # order first found
    assert merged[0]["content"] == "| Code | Report in |\n|---|---|\n| CBC | 6 hours |\n| LFT | 24 hours |"
    assert merged[0]["similarity"] == 0.6 and merged[0]["keyword_match"] is True


# ---------- ingestion ----------


async def test_ingest_marks_the_superseded_version(session_factory):
    async with session_factory() as session:
        docs = (await session.scalars(select(Document))).all()
        chunk_count = await session.scalar(select(func.count()).select_from(DocChunk))

    assert len(docs) == 10
    assert chunk_count == 123  # 78 heading sections, with every table row as its own chunk
    coverage = {d.version: d.is_current for d in docs if d.doc_id == "plan-coverage"}
    assert coverage == {1: False, 2: True}
    assert all(d.is_current for d in docs if d.doc_id != "plan-coverage")
    assert {d.society_id for d in docs if d.doc_id.startswith("annex-")} == set(SOCIETIES)
    assert all(d.society_id is None for d in docs if not d.doc_id.startswith("annex-"))


async def test_ingest_again_changes_nothing(session_factory, embedder):
    result = await ingest(session_factory, embedder)

    assert result["skipped"] is True


# ---------- the filters are in SQL, not applied afterwards ----------


def test_society_and_version_filters_are_in_the_where_clause():
    query = scoping.chunk_search_query(society_id="soc_lotus", query_embedding=[0.0] * 768, k=6)
    sql = str(query.compile(dialect=postgresql.dialect()))

    where = sql.split("WHERE", 1)[1].split("ORDER BY")[0]
    assert "documents.is_current IS true" in where
    assert "documents.society_id =" in where and "documents.society_id IS NULL" in where
    # ...and ranking and the cut to k come after the WHERE.
    assert sql.index("WHERE") < sql.index("ORDER BY") < sql.index("LIMIT")


def test_hybrid_search_reads_only_from_the_filtered_set():
    sql = " ".join(str(scoping.HYBRID_SEARCH_SQL).split())

    # The filters are in the WHERE clause of `visible`...
    visible = sql[sql.index("WITH visible AS (") : sql.index("dense AS (")]
    assert "WHERE d.is_current IS TRUE AND (d.society_id = :society_id OR d.society_id IS NULL)" in visible
    # ...and both searches take their chunks from `visible`, never from the table itself.
    dense = sql[sql.index("dense AS (") : sql.index("terms AS (")]
    keyword = sql[sql.index("term_weight AS (") : sql.index("keyword AS (")]
    assert "FROM visible" in dense and "doc_chunks" not in dense
    assert "visible v" in keyword and "doc_chunks" not in keyword
    assert "FULL OUTER JOIN" in sql


async def test_a_table_row_is_found_on_its_own_by_dense_search(session_factory, embedder):
    """Before rows were chunks, the whole nine-test table was one embedding and this missed."""
    (vector,) = await embedder.embed(["HbA1c report time"])

    async with session_factory() as session:
        dense = await scoping.search_chunks(session, society_id="soc_royal", query_embedding=vector, k=6)

    assert dense[0]["doc_id"] == "department-directory"
    assert "| `HBA1C` | HbA1c (glycated haemoglobin) | Blood (EDTA) | No | 24 hours |" in dense[0]["content"]


@pytest.mark.parametrize(
    "query, society_id, document, fact",
    [
        # The router's own wording for "CBC ki report kitni der mein aati hai". The row says
        # "Report in ... 6 hours"; nothing in it says "turnaround", so meaning alone misses it.
        ("CBC report turnaround time", "soc_lotus", "department-directory", "| `CBC` | Complete Blood Count | Blood (EDTA) | No | 6 hours |"),
        # One bullet in the Lotus Tower annex.
        ("dietitian teleconsultation covered", "soc_lotus", "annex-lotus-tower", "**Dietitian teleconsultation:** 4 per resident per plan year are covered."),
    ],
)
async def test_questions_dense_search_gets_wrong_and_hybrid_gets_right(
    session_factory, embedder, query, society_id, document, fact
):
    settings = get_settings()
    dense_tools = make_tools(session_factory, embedder, min_similarity=settings.retrieval_min_similarity, hybrid=False)
    hybrid_tools = make_tools(session_factory, embedder, min_similarity=settings.retrieval_min_similarity)

    dense = await search(dense_tools, query, society_id)
    hybrid = await search(hybrid_tools, query, society_id)

    assert not any(fact in p["content"] for p in dense)  # dense alone never surfaces the fact
    found = next(p for p in hybrid if fact in p["content"])
    assert found["doc_id"] == document and found["keyword_match"] is True


@pytest.mark.parametrize("society_id", SOCIETIES)
async def test_hybrid_search_never_returns_another_society_or_an_old_version(session_factory, embedder, society_id):
    query = "wellness room hours Sunday home sample collection vitamin D covered"
    (vector,) = await embedder.embed([query])

    async with session_factory() as session:
        found = await scoping.search_chunks(
            session, society_id=society_id, query_embedding=vector, k=40, query_text=query
        )

    assert len(found) == 40
    assert any(p["keyword_match"] for p in found) and not all(p["keyword_match"] for p in found)
    assert {p["society_id"] for p in found} <= {society_id, None}
    assert {p["version"] for p in found if p["doc_id"] == "plan-coverage"} <= {2}


async def test_a_query_with_no_usable_words_still_works(session_factory, embedder):
    # Hindi only: the English keyword search has nothing to match, dense search carries it.
    query = "रविवार को वेलनेस रूम कब खुलता है"
    (vector,) = await embedder.embed([query])

    async with session_factory() as session:
        found = await scoping.search_chunks(
            session, society_id="soc_lotus", query_embedding=vector, k=6, query_text=query
        )

    assert found[0]["doc_id"] == "annex-lotus-tower"


# ---------- society scoping: the immediate-no rule ----------


@pytest.mark.parametrize("society_id", SOCIETIES)
async def test_no_other_societys_document_is_ever_returned(session_factory, embedder, society_id):
    (question,) = await embedder.embed(["wellness room hours on Sunday, home sample collection charge"])

    async with session_factory() as session:
        visible = await scoping.search_chunks(
            session, society_id=society_id, query_embedding=question, k=EVERYTHING
        )

    assert {p["society_id"] for p in visible} == {society_id, None}
    annexes = {p["doc_id"] for p in visible if p["doc_id"].startswith("annex-")}
    assert len(annexes) == 1


async def test_the_same_question_gets_each_societys_own_answer(tools):
    question = "What time does the wellness room open on Sunday?"

    lotus = await search(tools, question, "soc_lotus")
    royal = await search(tools, question, "soc_royal")

    lotus_text = " ".join(p["content"] for p in lotus if p["doc_id"].startswith("annex-"))
    royal_text = " ".join(p["content"] for p in royal if p["doc_id"].startswith("annex-"))
    assert "Sunday | Closed" in lotus_text and "09:00 – 13:00" not in lotus_text
    assert "Sunday | 09:00 – 13:00" in royal_text and "Closed" not in royal_text


async def test_hindi_question_finds_the_patients_own_annex(tools):
    # The question from the bundle's Hindi fixture, asked by a Lotus Tower patient.
    passages = await search(tools, "रविवार को वेलनेस रूम कितने बजे खुलता है?", "soc_lotus")

    assert passages[0]["doc_id"] == "annex-lotus-tower"
    assert passages[0]["heading_path"].startswith("Society Annex — Lotus Tower")


# ---------- version: superseded documents are kept out of search ----------


@pytest.mark.parametrize("society_id", SOCIETIES)
async def test_superseded_version_is_never_returned(session_factory, embedder, society_id):
    (question,) = await embedder.embed(["Is the Vitamin D test covered?"])

    async with session_factory() as session:
        visible = await scoping.search_chunks(
            session, society_id=society_id, query_embedding=question, k=EVERYTHING
        )

    versions = {p["version"] for p in visible if p["doc_id"] == "plan-coverage"}
    assert versions == {2}


async def test_vitamin_d_answer_comes_from_version_2(tools):
    passages = await search(tools, "Is the Vitamin D test covered by my plan?", "soc_shivalik")

    top = passages[0]
    assert (top["doc_id"], top["version"]) == ("plan-coverage", 2)
    evidence = " ".join(p["content"] for p in passages if p["doc_id"] == "plan-coverage")
    assert "no longer covered" in evidence or "not covered; member rate ₹650" in evidence


# ---------- citations and abstention ----------


async def test_every_passage_can_be_cited(tools):
    passages = await search(tools, "How long are conversation transcripts kept?", "soc_royal")

    assert passages, "expected evidence for a question the corpus answers"
    for passage in passages:
        assert passage["doc_id"] and passage["title"] and passage["heading_path"]
    assert passages[0]["heading_path"] == "MicroHeal Clinic Policy > Privacy and consent > Retention"


@pytest.mark.parametrize(
    "question",
    ["Who won the cricket match yesterday?", "What is the wifi password?", "MRI scans available"],
)
async def test_question_outside_the_corpus_returns_no_evidence(tools, question):
    assert await search(tools, question, "soc_royal") == []


async def test_malformed_k_is_rejected(tools):
    result = await search(tools, "wellness room hours", "soc_lotus", k=0)

    assert result["error"]["code"] == "INVALID_ARGUMENTS"
