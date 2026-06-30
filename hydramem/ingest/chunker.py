"""MarkdownChunker — single responsibility: split Markdown text into chunks."""
from __future__ import annotations

import re


class MarkdownChunker:
    """Splits a Markdown document into overlapping, size-bounded chunks.

    Strategy (boundary-aware slicing inspired by MemPalace's ``chunk_text``
    [MIT], adapted to HydraMem's Markdown-first ingestion):

      1. Split by H1–H3 headers so each section starts on its heading.
      2. Emit any section that already fits within *max_tokens* unchanged.
      3. Hard-bound oversized sections: slice them into pieces no larger than
         the limit, breaking at the best available boundary (paragraph → line
         → sentence → word) and carrying *overlap_tokens* of trailing context
         into the next piece so a fact spanning a boundary stays retrievable.

    Unlike the previous implementation, **no chunk can exceed the limit** — a
    single giant paragraph is now sliced instead of emitted whole.

    Sizes use the 4-chars ≈ 1 token heuristic to avoid a tiktoken import at
    ingestion time (exact token counts are measured later).
    """

    def __init__(self, max_tokens: int = 400, overlap_tokens: int = 40) -> None:
        if max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {max_tokens}")
        self._max_chars = max_tokens * 4
        # Clamp overlap below half the window. An overlap ≥ the window would
        # stall the slicer (the infinite-loop foot-gun MemPalace guards against).
        self._overlap_chars = max(0, min(overlap_tokens, max_tokens // 2)) * 4
        self._header_pattern = re.compile(r"(?m)^#{1,3}\s+")

    def chunk(self, text: str) -> list[str]:
        """Return a list of non-empty chunk strings from *text*."""
        chunks: list[str] = []
        for section in self._header_pattern.split(text):
            section = section.strip()
            if section:
                chunks.extend(self._split_bounded(section))
        return [c for c in chunks if c.strip()]

    # ── Internals ────────────────────────────────────────────────────────────

    def _split_bounded(self, text: str) -> list[str]:
        """Slice *text* into ≤ max_chars pieces with boundary-aware overlap."""
        if len(text) <= self._max_chars:
            return [text]

        chunks: list[str] = []
        start = 0
        n = len(text)
        while start < n:
            end = min(start + self._max_chars, n)
            if end < n:
                end = self._best_boundary(text, start, end)
            piece = text[start:end].strip()
            if piece:
                chunks.append(piece)
            if end >= n:
                break
            # Advance, carrying overlap; the +1 floor guarantees progress even
            # if a boundary lands pathologically close to the window start.
            start = max(end - self._overlap_chars, start + 1)
        return chunks

    def _best_boundary(self, text: str, start: int, end: int) -> int:
        """Latest natural break in the back half of [start, end]; else *end*.

        Prefers a paragraph break, then a line break, then a sentence end,
        then a word boundary — mirroring MemPalace's ``rfind`` cascade.
        """
        floor = start + self._max_chars // 2
        for sep in ("\n\n", "\n", ". ", " "):
            idx = text.rfind(sep, floor, end)
            if idx != -1:
                return idx + len(sep)
        return end
