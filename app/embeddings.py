"""Gemini embeddings client (gemini-embedding-001) using the google-genai SDK.

Embeddings are normalized manually because gemini-embedding-001 does not
auto-normalize below 3072 dimensions (we use EMBEDDING_DIM=1536 to keep the
schema's vector(1536) column unchanged).
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Sequence

from google import genai
from google.genai import types

from .config import get_settings


@lru_cache
def get_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Return the (normalized) embedding vectors for a batch of texts."""
    if not texts:
        return []
    settings = get_settings()
    client = get_client()
    clean = [t.replace("\n", " ") if t is not None else "" for t in texts]
    response = client.models.embed_content(
        model=settings.gemini_embedding_model,
        contents=list(clean),
        config=types.EmbedContentConfig(
            output_dimensionality=settings.embedding_dim,
            task_type="RETRIEVAL_DOCUMENT",
        ),
    )
    return [_normalize(list(e.values)) for e in response.embeddings]


def embed_text(text: str) -> list[float]:
    """Return the normalized embedding vector for a single text (query)."""
    if not text:
        return []
    settings = get_settings()
    client = get_client()
    response = client.models.embed_content(
        model=settings.gemini_embedding_model,
        contents=[text.replace("\n", " ")],
        config=types.EmbedContentConfig(
            output_dimensionality=settings.embedding_dim,
            task_type="RETRIEVAL_QUERY",
        ),
    )
    return _normalize(list(response.embeddings[0].values))


def format_vector(vector: list[float]) -> str:
    """Render a float list as a Postgres vector literal `[1.0,2.0,...]`."""
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
