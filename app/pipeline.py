"""RAG pipeline orchestrator: ties retrieval and completion together.

Responsibilities:
- `run_rag`: full RAG flow (embed -> retrieve chunks -> complete -> score).
- `run_stuffed`: full-doc baseline (reconstruct text -> complete, no retrieval).
- `RagResult`: shared output dataclass consumed by the routers.

Neither function knows about HTTP; errors from lower layers propagate as-is.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from fastapi import HTTPException

from .completion import complete
from .config import get_settings
from .groundedness import classify_groundedness
from .retrieval import get_full_document_text, retrieve_chunks
from .schemas import ChatSource


@dataclass
class RagResult:
    """One branch of the comparison: the answer, its cost, and its evidence."""

    answer: str
    model: str
    latency_ms: int
    groundedness: str
    tokens_used: int
    sources: list[ChatSource] = field(default_factory=list)
    # None for the full-document branch: no retrieval happened, so there is no
    # similarity to report. 0.0 would be a lie that reads like "no match".
    retrieval_score: float | None = None
    context_chars: int = 0
    chunks_retrieved: int = 0


def run_rag(
    question: str, user_id: str, document_ids: list[str] | None = None
) -> RagResult:
    """Full RAG pipeline for a single question.

    1. Embed the question and retrieve the top-K matching chunks.
    2. If no chunks match, return a canned answer immediately.
    3. Otherwise, call the LLM with the retrieved context and score groundedness.
    """
    settings = get_settings()
    started = time.monotonic()
    matches, sources, context, scores = retrieve_chunks(
        question, user_id, document_ids=document_ids
    )

    if not matches:
        answer = (
            "I couldn't find any relevant information in your indexed documents. "
            "Try uploading more sources or rephrasing your question."
        )
        latency = int((time.monotonic() - started) * 1000)
        groundedness = classify_groundedness(None, answer=answer, context=[], question=question)
        primary_model = settings.groq_model if settings.groq_api_key else settings.gemini_model
        return RagResult(
            answer=answer,
            model=primary_model,
            latency_ms=latency,
            groundedness=groundedness,
            tokens_used=0,
            sources=[],
            retrieval_score=None,
            context_chars=0,
            chunks_retrieved=0,
        )

    retrieval_score = sum(scores) / len(scores) if scores else None
    completion = complete(question, context, mode="rag")
    latency = int((time.monotonic() - started) * 1000)
    groundedness = classify_groundedness(
        retrieval_score,
        answer=completion.answer,
        context=context,
        question=question,
    )

    return RagResult(
        answer=completion.answer,
        model=completion.model,
        latency_ms=latency,
        groundedness=groundedness,
        tokens_used=completion.tokens_used,
        sources=sources,
        retrieval_score=retrieval_score,
        context_chars=sum(len(c) for c in context),
        chunks_retrieved=len(sources),
    )


def run_stuffed(
    question: str, user_id: str, document_ids: list[str] | None = None
) -> RagResult:
    """Baseline that stuffs the entire (relevant) document into one LLM call.

    This is the anti-pattern RAG is meant to replace: no retrieval, the whole
    source is shoved into the prompt on every query. Returns a RagResult so it
    can be stored and compared like a normal RAG run.
    """
    settings = get_settings()
    started = time.monotonic()

    full_text, filenames = get_full_document_text(user_id, document_ids)
    if not full_text.strip():
        latency = int((time.monotonic() - started) * 1000)
        return RagResult(
            answer=(
                "There are no indexed documents to answer from. "
                "Upload a document first and try again."
            ),
            model=settings.groq_model if settings.groq_api_key else settings.gemini_model,
            latency_ms=latency,
            groundedness="Low",
            tokens_used=0,
            sources=[],
            retrieval_score=None,
            context_chars=0,
        )

    # The full-doc baseline shoves the entire corpus into one prompt, so the sum
    # of the selected documents must fit the LLM token budget. Single docs are
    # capped at upload time; this guard catches selected corpuses that exceed it.
    if len(full_text) > settings.max_document_chars:
        raise HTTPException(
            status_code=422,
            detail=(
                f"The selected corpus is {len(full_text)} characters, above the "
                f"{settings.max_document_chars}-character budget for the full-doc "
                "baseline (~6K tokens). Remove documents from the selection to "
                "fit the budget."
            ),
        )

    completion = complete(question, [full_text], mode="full-document")
    latency = int((time.monotonic() - started) * 1000)
    groundedness = classify_groundedness(
        None,
        answer=completion.answer,
        context=[full_text],
        question=question,
    )

    sources = [ChatSource(document=name, score=None) for name in filenames]

    return RagResult(
        answer=completion.answer,
        model=completion.model,
        latency_ms=latency,
        groundedness=groundedness,
        tokens_used=completion.tokens_used,
        sources=sources,
        retrieval_score=None,
        context_chars=len(full_text),
        chunks_retrieved=0,
    )
