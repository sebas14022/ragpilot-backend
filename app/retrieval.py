"""Vector retrieval layer: embed a question and fetch matching chunks from pgvector.

Responsibilities:
- Embed the incoming question with Gemini.
- Call the `match_documents` Supabase RPC to run the HNSW approximate-NN search.
- Map raw rows to typed ChatSource objects and resolve document filenames.
- `get_full_document_text` and `corpus_char_count` support the full-doc baseline.
"""

from __future__ import annotations

from .chunking import merge_chunks
from .config import get_settings
from .db import get_supabase
from .embeddings import embed_text, format_vector
from .schemas import ChatSource


def retrieve_chunks(
    question: str,
    user_id: str,
    top_k: int = 0,
    document_ids: list[str] | None = None,
) -> tuple[list[dict], list[ChatSource], list[str], list[float]]:
    """Embed *question* and run match_documents.

    Returns (matches, sources, context, scores).
    Optionally filters results to *document_ids* after the RPC call so the
    same HNSW index is used for all queries regardless of document selection.
    """
    settings = get_settings()
    sb = get_supabase()
    top_k = top_k or settings.rag_top_k

    query_vector = format_vector(embed_text(question))
    rpc_res = sb.rpc(
        "match_documents",
        {
            "query_embedding": query_vector,
            "match_count": top_k,
            "match_threshold": settings.rag_min_score,
            "p_user_id": user_id,
        },
    ).execute()

    matches = rpc_res.data or []
    if document_ids:
        wanted = set(document_ids)
        matches = [m for m in matches if m.get("document_id") in wanted]

    sources: list[ChatSource] = []
    context: list[str] = []
    scores: list[float] = []

    if not matches:
        return [], sources, context, scores

    doc_ids = {m["document_id"] for m in matches}
    doc_names: dict[str, str] = {}
    if doc_ids:
        names = (
            sb.table("documents")
            .select("id, filename")
            .in_("id", list(doc_ids))
            .execute()
        )
        doc_names = {r["id"]: r["filename"] for r in (names.data or [])}

    for m in matches:
        content = m.get("content") or ""
        context.append(content)
        score = float(m.get("similarity") or 0.0)
        scores.append(score)
        idx = m.get("chunk_index")
        sources.append(
            ChatSource(
                document=doc_names.get(m.get("document_id"), "document"),
                score=round(score, 4),
                section=(f"chunk {idx}" if idx is not None else None),
            )
        )

    return matches, sources, context, scores


def get_full_document_text(
    user_id: str, document_ids: list[str] | None = None
) -> tuple[str, list[str]]:
    """Reconstruct the full text of the user's documents from their stored chunks.

    Returns (full_text, doc_filenames). When *document_ids* is None, every
    indexed document is included -- the worst-case baseline scenario.
    """
    sb = get_supabase()

    base_query = (
        sb.table("document_chunks")
        .select("document_id, chunk_index, content")
        .eq("user_id", user_id)
        .order("chunk_index")
    )
    chunks_query = (
        base_query.in_("document_id", list(document_ids)).execute()
        if document_ids
        else base_query.execute()
    )

    rows = chunks_query.data or []

    by_doc: dict[str, list[str]] = {}
    for r in rows:
        by_doc.setdefault(r["document_id"], []).append(r.get("content") or "")

    doc_ids = list(by_doc.keys())
    doc_names: dict[str, str] = {}
    if doc_ids:
        names = (
            sb.table("documents")
            .select("id, filename")
            .in_("id", doc_ids)
            .execute()
        )
        doc_names = {r["id"]: r["filename"] for r in (names.data or [])}

    blocks: list[str] = []
    filenames: list[str] = []
    for did in doc_ids:
        # Chunks overlap so retrieval never loses a fact at a boundary; rejoining
        # them verbatim would duplicate that overlap and inflate the prompt.
        text = merge_chunks(by_doc[did])
        name = doc_names.get(did, "document")
        blocks.append(f"--- {name} ---\n{text}")
        filenames.append(name)

    return "\n\n".join(blocks), filenames


def corpus_char_count(
    user_id: str, document_ids: list[str] | None = None
) -> int:
    """Size of the exact string the full-doc baseline would send.

    The pre-flight budget check in `/compare` must measure what `run_stuffed`
    actually builds, otherwise a document can pass the upload gate and still be
    rejected later. Deriving it from `get_full_document_text` keeps one source
    of truth.
    """
    full_text, _ = get_full_document_text(user_id, document_ids)
    return len(full_text)
