"""LLM completion layer: prompt construction, provider dispatch, and retry logic.

Two prompt contracts, because the two branches of the comparison hand the model
different material:

- ``"rag"``: a handful of numbered passages, so ``[1]``/``[2]`` citations are
  meaningful and the model is asked to use them.
- ``"full-document"``: the whole corpus as one unnumbered blob. Numbering would
  be meaningless, so that contract forbids citation markers outright.

Either way, markers like ``【1†L71-L74】`` are stripped from the answer: no
document or prompt in this app produces them.

Responsibilities:
- Build the system/user message pair for a mode.
- Dispatch to Groq (primary) and fall back to Gemini, with exponential backoff
  on transient errors (429, 500, 503, TPM quota).
- Expose a single `complete()` function so callers never touch provider details.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Literal, Sequence

from fastapi import HTTPException
from google.genai import types

from .config import get_settings
from .embeddings import get_client

logger = logging.getLogger(__name__)

PromptMode = Literal["rag", "full-document"]

_ANSWER_FROM_EVIDENCE = (
    "Answer from what the material establishes. If it establishes that the "
    "requested thing does not exist, does not apply, or happens immediately, say "
    "that explicitly instead of calling it unspecified. Only report that the "
    "answer is missing when the material never touches the topic. "
    "Never invent facts, figures, line numbers, or citation formats."
)

_RAG_SYSTEM = (
    "You answer questions using only the numbered context passages supplied. "
    "Cite the passages you rely on as [1], [2], matching their numbers. "
    + _ANSWER_FROM_EVIDENCE
)

_FULL_DOCUMENT_SYSTEM = (
    "You answer questions using only the document text supplied. The text is not "
    "numbered: refer to documents by their filename if you cite them, and never "
    "emit bracketed citation markers or line numbers. "
    + _ANSWER_FROM_EVIDENCE
)

# Providers occasionally emit CMS-style markers such as 【1†L71-L74】. They appear
# in neither our prompts nor the source documents, so they are pure noise: the
# answer is shown next to its real sources, and a fabricated marker undermines it.
_FOREIGN_CITATION = re.compile(r"\s*【[^】]*】")


@dataclass(frozen=True)
class Completion:
    """One successful LLM call: the answer plus what it cost."""

    answer: str
    latency_ms: int
    tokens_used: int
    model: str


_RETRY_ATTEMPTS = 3
_RETRY_DELAYS = [0.5, 1.5, 3.5]

# Only retry on transient errors (429, 500, 503, and 413 when it is a Groq TPM
# quota roll). 404/400/401 are permanent. "tokens per minute" matches Groq's 413
# "Request too large ... tokens per minute (TPM)" which resets each minute.
_RETRYABLE_STRINGS = (
    "429",
    "500",
    "503",
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "tokens per minute",
)


def _is_transient(exc: Exception) -> bool:
    """Return True if the error is transient and worth retrying."""
    try:
        import groq as _groq

        if isinstance(exc, (_groq.RateLimitError, _groq.InternalServerError)):
            return True
    except ImportError:
        pass
    msg = str(exc)
    return any(code in msg for code in _RETRYABLE_STRINGS)


def build_messages(
    question: str, context: Sequence[str], *, mode: PromptMode = "rag"
) -> tuple[str, str]:
    """Return (system_instruction, user_prompt) for *mode*.

    ``"rag"`` numbers each passage so the answer can point at it; the
    full-document contract passes the corpus through untouched, because
    numbering a single stuffed blob only invites invented locations.
    """
    if mode == "rag":
        passages = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(context))
        return _RAG_SYSTEM, f"Context:\n{passages}\n\nQuestion: {question}\n\nAnswer:"

    documents = "\n\n".join(context)
    return _FULL_DOCUMENT_SYSTEM, f"Documents:\n{documents}\n\nQuestion: {question}\n\nAnswer:"


def strip_foreign_citations(answer: str) -> str:
    """Drop citation markers that no source document or prompt asked for."""
    return _FOREIGN_CITATION.sub("", answer).strip()


@lru_cache
def _get_groq_client():
    """Return a cached Groq client, or None if the API key is not configured."""
    import groq as _groq

    settings = get_settings()
    if not settings.groq_api_key:
        return None
    return _groq.Groq(api_key=settings.groq_api_key)


def _call_groq(system: str, user: str) -> tuple[str, int, str]:
    """Call Groq. Returns (answer, tokens, model_name). Raises on failure."""
    client = _get_groq_client()
    if client is None:
        raise RuntimeError("Groq API key not configured")
    settings = get_settings()
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    answer = (response.choices[0].message.content or "").strip()
    usage = response.usage
    tokens = (usage.prompt_tokens or 0) + (usage.completion_tokens or 0) if usage else 0
    return answer, tokens, settings.groq_model


def _call_gemini(system: str, user: str) -> tuple[str, int, str]:
    """Call Gemini. Returns (answer, tokens, model_name). Raises on failure."""
    client = get_client()
    settings = get_settings()
    chat = client.models.generate_content(
        model=settings.gemini_model,
        contents=[types.Part.from_text(text=user)],
        config=types.GenerateContentConfig(system_instruction=system, temperature=0.2),
    )
    answer = (getattr(chat, "text", None) or "").strip()
    usage = getattr(chat, "usage_metadata", None)
    tokens = 0
    if usage is not None:
        tokens = int(getattr(usage, "total_token_count", 0) or 0)
    return answer, tokens, settings.gemini_model


ProviderFn = Callable[[str, str], tuple[str, int, str]]


def complete(
    question: str, context: Sequence[str], *, mode: PromptMode = "rag"
) -> Completion:
    """Build a prompt for *mode* and call the best available provider with retry.

    Tries Groq first (if configured), then Gemini. Raises HTTP 502 if all
    providers exhaust their retry budgets.
    """
    settings = get_settings()
    system, user = build_messages(question, context, mode=mode)

    providers: list[tuple[str, ProviderFn]] = []
    if settings.groq_api_key:
        providers.append(("Groq", _call_groq))
    providers.append(("Gemini", _call_gemini))

    started = time.monotonic()
    last_error: Exception | None = None

    for provider_name, provider_fn in providers:
        for attempt in range(_RETRY_ATTEMPTS):
            attempt_started = time.monotonic()
            try:
                answer, tokens, model_name = provider_fn(system, user)
                answer = strip_foreign_citations(answer)
                # Measure only the successful attempt's latency, not retries/backoff.
                latency = int((time.monotonic() - attempt_started) * 1000)
                return Completion(
                    answer=answer,
                    latency_ms=latency,
                    tokens_used=tokens,
                    model=model_name,
                )
            except Exception as exc:
                last_error = exc
                transient = _is_transient(exc)
                if transient and attempt < _RETRY_ATTEMPTS - 1:
                    delay = _RETRY_DELAYS[attempt]
                    logger.warning(
                        "%s attempt %d failed (%s), retrying in %.1fs",
                        provider_name, attempt + 1, exc, delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "%s failed%s: %s",
                        provider_name,
                        f" after {attempt + 1} attempts" if attempt > 0 else "",
                        exc,
                    )
                    break

    latency = int((time.monotonic() - started) * 1000)
    raise HTTPException(
        status_code=502,
        detail=f"All LLM providers failed. Last error: {last_error}",
    )
