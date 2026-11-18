"""Load data/corpus/*.md into documents and doc_chunks.

Run with:  python -m app.ingest          (skips if the files have not changed)
           python -m app.ingest --force  (re-embed everything)

Ingestion replaces the whole corpus in one transaction, so search never sees a
half-loaded state. A superseded version is still stored, but marked
is_current = false, and search only reads current rows.

This is an offline admin job with no patient involved. Its one read of the
documents table (the file hashes, to decide whether to skip) is the only
document read outside app/scoping.py.
"""

import asyncio
import hashlib
import sys
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.corpus import CorpusDocument, parse_document
from app.db.models import DocChunk, Document
from app.db.session import make_engine, make_session_factory
from app.embeddings import Embedder

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"


def is_current(doc: CorpusDocument, latest_version: dict[str, int]) -> bool:
    """Current means: nothing replaced it, and no newer version of the same doc_id exists."""
    return doc.superseded_by is None and doc.version == latest_version[doc.doc_id]


async def ingest(
    session_factory: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    corpus_dir: Path = CORPUS_DIR,
    *,
    force: bool = False,
) -> dict:
    files = {path.name: path.read_text(encoding="utf-8") for path in sorted(corpus_dir.glob("*.md"))}
    hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()}

    async with session_factory() as session:
        stored = dict((await session.execute(select(Document.source_path, Document.source_sha256))).all())
    if stored == hashes and not force:
        return {"skipped": True, "documents": len(stored)}

    docs = {name: parse_document(text) for name, text in files.items()}
    latest_version: dict[str, int] = {}
    for doc in docs.values():
        latest_version[doc.doc_id] = max(doc.version, latest_version.get(doc.doc_id, 0))

    # Embed every chunk in one batch, before opening the write transaction.
    all_chunks = [chunk for doc in docs.values() for chunk in doc.chunks]
    vectors = iter(await embedder.embed([chunk.text_to_embed for chunk in all_chunks]))

    async with session_factory() as session, session.begin():
        await session.execute(delete(Document))  # chunks go with it (ON DELETE CASCADE)
        for name, doc in docs.items():
            row = Document(
                doc_id=doc.doc_id,
                version=doc.version,
                title=doc.title,
                society_id=doc.society_id,
                effective_from=doc.effective_from,
                superseded_by=doc.superseded_by,
                is_current=is_current(doc, latest_version),
                source_path=name,
                source_sha256=hashes[name],
            )
            session.add(row)
            await session.flush()  # assigns row.id
            session.add_all(
                DocChunk(
                    document_id=row.id,
                    chunk_index=index,
                    heading_path=chunk.heading_path,
                    content=chunk.content,
                    embedding=next(vectors),
                )
                for index, chunk in enumerate(doc.chunks)
            )
    return {"skipped": False, "documents": len(docs), "chunks": len(all_chunks)}


async def main() -> None:
    engine = make_engine(get_settings())
    try:
        result = await ingest(make_session_factory(engine), Embedder(), force="--force" in sys.argv)
        print(f"ingested: {result}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
