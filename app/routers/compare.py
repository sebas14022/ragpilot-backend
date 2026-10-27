"""RAG (with retrieval) vs stuffed-baseline (LLM with the whole document).

The comparison is honest: both paths give the LLM access to the user's
documents. RAG retrieves only the relevant chunks; the baseline stuffs the
entire document into a single prompt (the anti-pattern RAG replaces).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_user, UserContext
from ..config import get_settings
from ..db import get_supabase
from ..pipeline import RagResult
from ..rag_service import corpus_char_count, run_rag, run_stuffed
from ..schemas import ComparisonAnswer, ComparisonResult, ContextUsage

router = APIRouter()
logger = logging.getLogger(__name__)


class CompareInput(BaseModel):
    query: str
    documentIds: list[str] | None = None


@router.post("/compare", response_model=ComparisonResult)
def compare(payload: CompareInput, user: UserContext = Depends(require_user)) -> ComparisonResult:
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    sb = get_supabase()

    # Fail fast: the full-doc baseline stuffs the whole selection into one prompt,
    # so the total corpus must fit the LLM token budget before we run anything.
    total_chars = corpus_char_count(user.user_id, payload.documentIds)
    budget = get_settings().max_document_chars
    if total_chars > budget:
        raise HTTPException(
            status_code=422,
            detail=(
                f"The selected corpus is {total_chars} characters, above the "
                f"{budget}-character budget for the full-doc baseline "
                "(~6K tokens). Remove documents from the selection to fit "
                "the budget."
            ),
        )

    rag = run_rag(query, user.user_id, document_ids=payload.documentIds)
    baseline = run_stuffed(query, user.user_id, document_ids=payload.documentIds)

    def context_usage(
        result: RagResult, *, kind: Literal["retrieval", "full-document"]
    ) -> ContextUsage:
        documents = {s.document for s in result.sources}
        return ContextUsage(
            kind=kind,
            chunks=len(result.sources) if kind == "retrieval" else 0,
            documents=len(documents),
            characters=result.context_chars,
            avgSimilarity=result.retrieval_score if kind == "retrieval" else None,
        )

    def to_answer(
        label: str, result: RagResult, *, kind: Literal["retrieval", "full-document"]
    ) -> ComparisonAnswer:
        return ComparisonAnswer(
            label=label,
            model=result.model,
            latencyMs=result.latency_ms,
            groundedness=result.groundedness,
            tokensUsed=result.tokens_used,
            context=context_usage(result, kind=kind),
            sources=result.sources,
            answer=result.answer,
        )

    rag_answer = to_answer("RAG", rag, kind="retrieval")
    baseline_answer = to_answer("Full-doc", baseline, kind="full-document")

    # Persist to `comparisons` (per-question metrics) and `queries` (dashboard
    # counters for Recent Queries / query and token totals).
    try:
        sb.table("comparisons").insert(
            {
                "user_id": user.user_id,
                "query": query,
                "rag_answer": rag.answer,
                "rag_model": rag.model,
                "rag_latency_ms": rag.latency_ms,
                "rag_groundedness": rag.groundedness,
                "rag_tokens_used": rag.tokens_used,
                "baseline_answer": baseline.answer,
                "baseline_model": baseline.model,
                "baseline_latency_ms": baseline.latency_ms,
                "baseline_groundedness": baseline.groundedness,
                "baseline_tokens_used": baseline.tokens_used,
            }
        ).execute()
    except Exception as exc:
        logger.error("Failed to persist comparison for user %s: %s", user.user_id, exc)

    try:
        sb.table("queries").insert(
            {
                "user_id": user.user_id,
                "question": query,
                "answer": rag.answer,
                "model": rag.model,
                "latency_ms": rag.latency_ms,
                "groundedness": rag.groundedness,
                "tokens_used": rag.tokens_used,
                "chunks_retrieved": rag.chunks_retrieved,
                "status": "success",
            }
        ).execute()
    except Exception as exc:
        logger.error("Failed to persist query for user %s: %s", user.user_id, exc)

    return ComparisonResult(query=query, rag=rag_answer, baseline=baseline_answer)
