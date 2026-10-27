"""Backward-compatibility shim for rag_service.

The RAG logic has been split into focused modules:
  - app.retrieval   -- vector search, chunk-to-source mapping, full-doc reconstruction
  - app.completion  -- LLM provider dispatch, prompt building, retry/backoff
  - app.pipeline    -- run_rag / run_stuffed orchestration, RagResult dataclass

This module re-exports everything routers and tests imported directly from
rag_service so no call-site changes are required.
"""

from __future__ import annotations

# Re-exports -- kept for backward compatibility with existing routers and tests.
from .completion import complete, _is_transient          # noqa: F401
from .pipeline import RagResult, run_rag, run_stuffed    # noqa: F401
from .retrieval import (                                  # noqa: F401
    corpus_char_count,
    get_full_document_text,
    retrieve_chunks,
)
from .schemas import ChatSource                           # noqa: F401
