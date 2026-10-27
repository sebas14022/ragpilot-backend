"""Groundedness evaluation: hybrid heuristic + optional LLM fallback.

- Fast path (retrieval branches): derive a label from the average cosine
  similarity of the retrieved chunks using configured thresholds.
- Content path (branches without retrieval, or the ambiguous band): ask a cheap
  LLM whether the answer is actually supported by the context.

The two paths exist because similarity only exists when retrieval happened; the
full-document baseline has no retrieval score, and refusing to judge it would
make every comparison dishonest in RAG's favour.
"""

from __future__ import annotations

import logging
from typing import Sequence

from .config import get_settings
from .schemas import Groundedness

logger = logging.getLogger(__name__)


def groundedness_from_score(avg_score: float) -> Groundedness:
    settings = get_settings()
    if avg_score >= settings.grounded_high:
        return "High"
    if avg_score >= settings.grounded_medium:
        return "Medium"
    return "Low"


def classify_groundedness(
    retrieval_score: float | None,
    *,
    answer: str,
    context: Sequence[str],
    question: str,
) -> Groundedness:
    """Label how well *answer* is supported by *context*.

    *retrieval_score* is the average similarity of the chunks that were
    retrieved; pass ``None`` when nothing was retrieved (the full-document
    baseline) and the answer is judged on its content instead.
    """
    if not context:
        return "Low"

    heuristic = (
        groundedness_from_score(retrieval_score)
        if retrieval_score is not None
        else "Medium"
    )

    # A decisive similarity score is trusted; no extra LLM call.
    if retrieval_score is not None and heuristic in ("High", "Low"):
        return heuristic

    if not get_settings().groundedness_llm_fallback:
        return heuristic

    try:
        return _llm_groundedness_check(answer=answer, context=context, question=question)
    except Exception as exc:  # provider outage must not fail the request
        logger.warning("Groundedness check failed, falling back to %s: %s", heuristic, exc)
        return heuristic


def _llm_groundedness_check(*, answer: str, context: Sequence[str], question: str) -> Groundedness:
    from google.genai import types

    from .config import get_settings
    from .embeddings import get_client

    settings = get_settings()
    client = get_client()
    ctx = "\n---\n".join(context)[:8000]
    system = (
        "You evaluate whether an answer is supported by the given context. "
        "Reply with exactly one word: High, Medium, or Low. "
        "High = answer is fully supported by the context; "
        "Medium = partially supported; Low = not supported."
    )
    user = f"Question: {question}\n\nContext:\n{ctx}\n\nAnswer:\n{answer}"
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=[types.Part.from_text(text=user)],
        config=types.GenerateContentConfig(system_instruction=system, temperature=0),
    )
    text = (getattr(response, "text", None) or "").strip().lower()
    if "high" in text:
        return "High"
    if "low" in text:
        return "Low"
    return "Medium"
