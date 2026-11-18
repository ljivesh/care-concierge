"""Reading a corpus file: front-matter, then one chunk per heading. No database, no model.

A chunk is the text directly under one heading, up to the next heading of any
level. Its `heading_path` is the trail of headings above it, for example
"Society Annex — Lotus Tower > Wellness room > Hours". That path is what a
citation points at.
"""

import re
from dataclasses import dataclass
from datetime import date

import yaml

HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
PATH_SEPARATOR = " > "


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


def chunk_by_headings(body: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    path: list[str] = []  # headings we are currently inside, outermost first
    lines: list[str] = []

    def close_section() -> None:
        content = "\n".join(lines).strip()
        if content:  # a heading followed straight by a sub-heading has no text of its own
            chunks.append(Chunk(PATH_SEPARATOR.join(path), content))
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
