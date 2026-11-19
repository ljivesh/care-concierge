"""Reading a corpus file: front-matter, then chunks under each heading. No database, no model.

Chunks are cut on headings. The text directly under a heading is one chunk, and
each row of a table under it is a chunk of its own, with the table's header
repeated. A table of nine tests would otherwise be one chunk whose embedding
averages nine unrelated facts, and a question about one test would not find it.

Every chunk carries its `heading_path`, the trail of headings above it, for
example "Society Annex — Lotus Tower > Wellness room > Hours". That path is
what a citation points at, so a row is cited by the heading its table sits under.
"""

import re
from dataclasses import dataclass
from datetime import date

import yaml

HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
TABLE_DIVIDER = re.compile(r"^\|[\s:|-]+\|$")  # the |---|---| line under a table's header
PATH_SEPARATOR = " > "
# Bump when chunking changes, so ingestion re-chunks files whose text did not change.
CHUNKER_VERSION = "2"


@dataclass(frozen=True)
class Chunk:
    heading_path: str
    content: str

    @property
    def text_to_embed(self) -> str:
        # The heading path goes in too: "Hours" alone says nothing about which society.
        return f"{self.heading_path}\n{self.content}"


@dataclass(frozen=True)
class CorpusDocument:
    doc_id: str
    title: str
    version: int
    society_id: str | None  # None = applies to all societies
    effective_from: date
    superseded_by: str | None
    chunks: list[Chunk]


def split_front_matter(text: str) -> tuple[dict, str]:
    """The file starts with '---', YAML, '---'. Returns (metadata, the rest)."""
    _, front, body = text.split("---", 2)
    return yaml.safe_load(front), body


def split_tables(lines: list[str]) -> tuple[str, list[str]]:
    """Separate a section's lines into its prose and one text block per table row.

    A row block is the table's header line, its divider line, and that row, so the
    row still says what each column means when it is read on its own.
    """
    prose: list[str] = []
    rows: list[str] = []
    index = 0
    while index < len(lines):
        is_table_start = (
            lines[index].startswith("|")
            and index + 1 < len(lines)
            and TABLE_DIVIDER.match(lines[index + 1].strip())
        )
        if not is_table_start:
            prose.append(lines[index])
            index += 1
            continue
        header, divider = lines[index], lines[index + 1]
        index += 2
        while index < len(lines) and lines[index].startswith("|"):
            rows.append(f"{header}\n{divider}\n{lines[index]}")
            index += 1
    return "\n".join(prose).strip(), rows


def chunk_by_headings(body: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    path: list[str] = []  # headings we are currently inside, outermost first
    lines: list[str] = []

    def close_section() -> None:
        heading_path = PATH_SEPARATOR.join(path)
        prose, rows = split_tables(lines)
        if prose:  # a heading followed straight by a sub-heading has no text of its own
            chunks.append(Chunk(heading_path, prose))
        chunks.extend(Chunk(heading_path, row) for row in rows)
        lines.clear()

    for line in body.splitlines():
        heading = HEADING.match(line)
        if heading:
            close_section()
            level = len(heading.group(1))
            # A level-2 heading replaces any earlier level-2 and drops deeper ones.
            path = path[: level - 1] + [heading.group(2)]
        else:
            lines.append(line)
    close_section()
    return chunks


def merge_by_heading(chunks: list[dict]) -> list[dict]:
    """Chunks found under the same heading become one passage, in the order first found.

    Search returns rows one by one; the reader should see one source per heading,
    with the table header once and the matching rows under it.
    """
    passages: dict[tuple, dict] = {}
    for chunk in chunks:
        key = (chunk["doc_id"], chunk["version"], chunk["heading_path"])
        if key not in passages:
            passages[key] = {**chunk, "content": ""}
        passage = passages[key]
        seen = set(passage["content"].splitlines())
        fresh = [line for line in chunk["content"].splitlines() if line not in seen or not line.strip()]
        passage["content"] = "\n".join(filter(None, [passage["content"], "\n".join(fresh).strip()]))
        passage["similarity"] = max(passage["similarity"], chunk["similarity"])
        passage["keyword_match"] = passage["keyword_match"] or chunk["keyword_match"]
    return list(passages.values())


def parse_document(text: str) -> CorpusDocument:
    meta, body = split_front_matter(text)
    applies_to = meta["applies_to"]
    return CorpusDocument(
        doc_id=meta["doc_id"],
        title=meta["title"],
        version=int(meta["version"]),
        society_id=None if applies_to == "all" else applies_to,
        effective_from=meta["effective_from"],
        superseded_by=meta.get("superseded_by"),
        chunks=chunk_by_headings(body),
    )
