"""Text chunking strategies for indexing RAG documents."""

from __future__ import annotations

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 150


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> list[str]:
    """Split text into fixed-size chunks with overlap.

    Overlap reduces information loss across chunk boundaries. Paragraph-aware
    heuristic keeps chunks aligned to sentence/paragraph breaks where cheap.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)

        # Try to snap the end to a paragraph/sentence boundary for cleaner chunks.
        if end < n:
            window = text[start:end]
            boundary = _find_boundary(window)
            if boundary is not None:
                end = start + boundary

        chunks.append(text[start:end].strip())
        if end >= n:
            break

        start = max(start + overlap, end - overlap)
        if start >= end:
            start = end

    return [c for c in chunks if c]


def _find_boundary(window: str) -> int | None:
    """Return an index near the end of `window` at a natural break, or None."""
    # Prefer double-newline (paragraph), then newline, then sentence end.
    for token in ("\n\n", "\n", ". ", "! ", "? "):
        idx = window.rfind(token)
        if idx != -1 and idx > len(window) * 0.6:
            return idx + (1 if token in (". ", "! ", "? ") else 0) + 1
    return None


def merge_chunks(chunks: list[str]) -> str:
    """Rebuild one text from overlapping chunks (the inverse of `chunk_text`).

    Chunks overlap on purpose so retrieval never loses a fact across a boundary.
    Concatenating them naively duplicates that overlap, which inflates the
    full-document baseline by ~20% and can push a document over the prompt
    budget it already passed at upload time. Here each chunk is joined at the
    longest suffix of the text built so far that also prefixes the next chunk.
    """
    if not chunks:
        return ""

    merged = chunks[0]
    for chunk in chunks[1:]:
        overlap = _overlap_length(merged, chunk)
        merged += chunk[overlap:] if overlap else f"\n\n{chunk}"
    return merged


def _overlap_length(existing: str, upcoming: str, *, limit: int = DEFAULT_OVERLAP) -> int:
    """Longest suffix of *existing* that is also a prefix of *upcoming*.

    Bounded by the overlap `chunk_text` can actually produce, so repetitive
    content cannot make the merge cut more than one real overlap.
    """
    max_len = min(limit, len(existing), len(upcoming))
    for length in range(max_len, 0, -1):
        if existing.endswith(upcoming[:length]):
            return length
    return 0
