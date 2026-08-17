"""Splitting pages into retrievable chunks.

Doc 07 M5: *"Chunk with source and page retained."* Doc 06 §4.1 puts those
fields on the chunk record; doc 01 M8 explains why they matter — every price in
a generated proposal cites the document and page it came from, and that is the
highest-liability module in the product.

So a chunk that loses its page is not a slightly-degraded chunk. It is a chunk
that cannot be cited, which means it cannot ground a proposal.

**Chunks never span pages.** Merging the end of page 3 with the start of page 4
would produce a passage whose citation is a lie for half its content. Small
trailing chunks are accepted instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.documents.parse import Page

# Sized for the retrieval model rather than for tidiness: large enough that a
# price and its label stay together, small enough that a match is specific.
TARGET_CHARS = 1200
OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 50

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    page_number: int
    page_label: str | None
    ordinal: int
    """Position within the document, for stable ordering and de-duplication."""
    char_start: int
    char_end: int

    @property
    def citation(self) -> str:
        """What the user sees next to a generated figure."""
        if self.page_label:
            return f"{self.page_label} (page {self.page_number})"
        return f"page {self.page_number}"


def _split_long(text: str, limit: int) -> list[str]:
    """Break an oversized block at a sentence boundary, then anywhere."""
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    for sentence in _SENTENCE_END.split(text):
        if not parts or len(parts[-1]) + len(sentence) + 1 > limit:
            parts.append(sentence)
        else:
            parts[-1] = f"{parts[-1]} {sentence}"

    # A single sentence longer than the limit still has to be cut. A table row
    # or a minified block will do this.
    result: list[str] = []
    for part in parts:
        while len(part) > limit:
            result.append(part[:limit])
            part = part[limit:]
        if part:
            result.append(part)
    return result


def chunk_page(page: Page, *, start_ordinal: int = 0) -> list[Chunk]:
    """Split one page. The page number is attached at construction, not later."""
    text = page.text.strip()
    if not text:
        return []

    blocks = [b.strip() for b in _PARAGRAPH_BREAK.split(text) if b.strip()]
    if not blocks:
        blocks = [text]

    pieces: list[str] = []
    for block in blocks:
        for part in _split_long(block, TARGET_CHARS):
            if pieces and len(pieces[-1]) + len(part) + 2 <= TARGET_CHARS:
                pieces[-1] = f"{pieces[-1]}\n\n{part}"
            else:
                pieces.append(part)

    # A trailing fragment is folded back rather than stored alone: "OMR 3,200"
    # on its own is unretrievable, and worse, citable.
    if len(pieces) > 1 and len(pieces[-1]) < MIN_CHUNK_CHARS:
        pieces[-2] = f"{pieces[-2]}\n\n{pieces.pop()}"

    chunks: list[Chunk] = []
    cursor = 0
    for offset, piece in enumerate(pieces):
        start = text.find(piece, cursor)
        if start == -1:
            start = cursor
        end = start + len(piece)
        cursor = max(cursor, end - OVERLAP_CHARS)

        chunks.append(
            Chunk(
                text=piece,
                page_number=page.number,
                page_label=page.label,
                ordinal=start_ordinal + offset,
                char_start=start,
                char_end=end,
            )
        )
    return chunks


def chunk_document(pages: tuple[Page, ...]) -> list[Chunk]:
    """Chunk every page, never merging across a page boundary.

    A chunk spanning pages 3 and 4 would carry one citation for two sources —
    accurate for half its content and wrong for the rest, with no way for a
    reader to tell which half.
    """
    chunks: list[Chunk] = []
    for page in pages:
        chunks.extend(chunk_page(page, start_ordinal=len(chunks)))
    return chunks
