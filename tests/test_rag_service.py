"""Tests for the shared RAG pipeline (retrieve_chunks / run_rag).

Covers:
- the document_ids filter added to `retrieve_chunks` / `run_rag`
- the full retrieve -> prompt -> generate path, with and without matches

All tests use mocks: no Supabase, network, or Gemini calls are made.

Monkeypatch targets point to the module where each symbol is *used*, not where
it was defined (Python's monkeypatch rule).
"""

from __future__ import annotations

import pytest

import app.rag_service as rs
from app.completion import Completion


def _completion(answer="ans", latency_ms=10, tokens_used=5, model="openai/gpt-oss-120b"):
    """Build the dataclass `complete()` returns, for monkeypatched call sites."""
    return Completion(
        answer=answer, latency_ms=latency_ms, tokens_used=tokens_used, model=model
    )


class _Settings:
    rag_top_k = 5
    rag_min_score = 0.25
    grounded_high = 0.72
    grounded_medium = 0.48
    groundedness_llm_fallback = True
    gemini_model = "gemini-3.6-flash"
    groq_api_key = ""
    groq_model = "openai/gpt-oss-120b"
    max_document_chars = 24000


def _matches():
    """Three chunks across two documents: doc-a (2) and doc-b (1)."""
    return [
        {"document_id": "doc-a", "chunk_index": 0, "content": "a0", "similarity": 0.8},
        {"document_id": "doc-a", "chunk_index": 1, "content": "a1", "similarity": 0.7},
        {"document_id": "doc-b", "chunk_index": 0, "content": "b0", "similarity": 0.6},
    ]


class _FakeTable:
    def __init__(self, rows):
        self._rows = list(rows)

    def select(self, *cols):
        return self

    def in_(self, col, values):
        return self

    def execute(self):
        class _R:
            data = self._rows
        return _R()


class _FakeRpc:
    def __init__(self, data, captured=None):
        self._data = data
        self._captured = captured

    def execute(self):
        class _R:
            data = self._data
        return _R()


class _FakeSb:
    def __init__(self, matches, captured=None):
        self._matches = matches
        self._captured = captured if captured is not None else {}

    def rpc(self, name, params):
        self._captured["rpc_name"] = name
        self._captured["rpc_params"] = params
        return _FakeRpc(self._matches, self._captured)

    def table(self, name):
        names = [
            {"id": "doc-a", "filename": "one.pdf"},
            {"id": "doc-b", "filename": "two.pdf"},
        ]
        return _FakeTable(names)


def _patch(monkeypatch, *, matches, doc_ids, captured=None):
    """Patch retrieval-layer symbols where they are used (app.retrieval)."""
    settings = _Settings()
    monkeypatch.setattr("app.retrieval.get_settings", lambda: settings)
    monkeypatch.setattr("app.retrieval.get_supabase", lambda: _FakeSb(matches, captured))
    monkeypatch.setattr("app.retrieval.embed_text", lambda q: [0.1, 0.2])
    monkeypatch.setattr("app.retrieval.format_vector", lambda v: "[0.1,0.2]")
    return doc_ids


def test_filters_by_document_ids(monkeypatch):
    doc_ids = _patch(monkeypatch, matches=_matches(), doc_ids=["doc-a"])

    matches, sources, context, scores = rs.retrieve_chunks("q", "user-1", document_ids=doc_ids)

    assert len(matches) == 2
    assert {m["document_id"] for m in matches} == {"doc-a"}
    assert context == ["a0", "a1"]
    assert sources[0].document == "one.pdf"


def test_empty_document_ids_keeps_all(monkeypatch):
    _patch(monkeypatch, matches=_matches(), doc_ids=[])

    matches, sources, context, scores = rs.retrieve_chunks("q", "user-1", document_ids=[])

    assert len(matches) == 3


def test_none_document_ids_keeps_all(monkeypatch):
    _patch(monkeypatch, matches=_matches(), doc_ids=None)

    matches, sources, context, scores = rs.retrieve_chunks("q", "user-1", document_ids=None)

    assert len(matches) == 3


def test_filter_excluding_all_returns_empty(monkeypatch):
    _patch(monkeypatch, matches=_matches(), doc_ids=["doc-c"])

    matches, sources, context, scores = rs.retrieve_chunks("q", "user-1", document_ids=["doc-c"])

    assert matches == []
    assert sources == []
    assert context == []
    assert scores == []


def test_run_rag_forwards_document_ids(monkeypatch):
    """run_rag must pass document_ids down to retrieve_chunks."""
    _patch(monkeypatch, matches=_matches(), doc_ids=["doc-b"])

    captured = {}

    def fake_retrieve(question, user_id, **kwargs):
        captured["kwargs"] = kwargs
        # Emulate a retrieve that only kept doc-b.
        return (
            [{"document_id": "doc-b", "chunk_index": 0, "content": "b0", "similarity": 0.6}],
            [rs.ChatSource(document="two.pdf", score=0.6, section="chunk 0")],
            ["b0"],
            [0.6],
        )

    # run_rag lives in app.pipeline; patch symbols where they are used there.
    monkeypatch.setattr("app.pipeline.retrieve_chunks", fake_retrieve)
    monkeypatch.setattr(
        "app.pipeline.complete",
        lambda q, c, mode="rag": _completion("ans", 10, 5, "groq-openai/gpt-oss-120b"),
    )
    monkeypatch.setattr("app.pipeline.classify_groundedness", lambda *a, **k: "High")

    result = rs.run_rag("q", "user-1", document_ids=["doc-b"])

    assert captured["kwargs"]["document_ids"] == ["doc-b"]
    assert result.sources[0].document == "two.pdf"
    assert result.chunks_retrieved == 1


def test_retrieve_chunks_builds_sources_context_and_calls_rpc(monkeypatch):
    """Full happy-path retrieve: RPC params, source mapping, context, scores."""
    captured = {}
    _patch(monkeypatch, matches=_matches(), doc_ids=None, captured=captured)

    matches, sources, context, scores = rs.retrieve_chunks("q", "user-1")

    # RPC was invoked with the expected payload.
    assert captured["rpc_name"] == "match_documents"
    params = captured["rpc_params"]
    assert params["query_embedding"] == "[0.1,0.2]"
    assert params["match_count"] == 5
    assert params["match_threshold"] == 0.25
    assert params["p_user_id"] == "user-1"

    # All three matches survive when no document filter is given.
    assert len(matches) == 3
    assert context == ["a0", "a1", "b0"]
    assert scores == [0.8, 0.7, 0.6]

    # Sources map document_id -> filename and chunk_index -> section.
    assert sources[0].document == "one.pdf"
    assert sources[0].section == "chunk 0"
    assert sources[0].score == 0.8
    assert sources[2].document == "two.pdf"
    assert sources[2].section == "chunk 0"


def test_retrieve_chunks_no_matches_returns_empty(monkeypatch):
    """When the RPC returns nothing, all four outputs are empty."""
    _patch(monkeypatch, matches=[], doc_ids=None)

    matches, sources, context, scores = rs.retrieve_chunks("q", "user-1")

    assert matches == []
    assert sources == []
    assert context == []
    assert scores == []


def test_run_rag_without_matches_returns_canned_answer(monkeypatch):
    """No context -> canned answer, zero tokens, zero chunks, groundedness Low."""
    _patch(monkeypatch, matches=[], doc_ids=None)
    monkeypatch.setattr(
        "app.pipeline.retrieve_chunks",
        lambda q, uid, document_ids=None: ([], [], [], []),
    )

    grounded_calls = {}
    monkeypatch.setattr(
        "app.pipeline.classify_groundedness",
        lambda score, **k: grounded_calls.setdefault("score", score) or "Low",
    )
    monkeypatch.setattr("app.pipeline.get_settings", lambda: _Settings())

    result = rs.run_rag("q", "user-1")

    assert "couldn't find any relevant information" in result.answer
    assert result.tokens_used == 0
    assert result.chunks_retrieved == 0
    assert result.retrieval_score is None
    assert result.context_chars == 0
    assert result.sources == []
    assert result.groundedness == "Low"
    # No retrieval happened, so groundedness is judged without a score.
    assert grounded_calls.get("score") is None


def test_run_rag_full_pipeline_with_matches(monkeypatch):
    """Happy path: retrieve -> complete -> RagResult with real metrics."""
    _patch(monkeypatch, matches=_matches(), doc_ids=None)
    monkeypatch.setattr(
        "app.pipeline.retrieve_chunks",
        lambda q, uid, document_ids=None: (
            _matches(),
            [
                rs.ChatSource(document="one.pdf", score=0.8, section="chunk 0"),
                rs.ChatSource(document="one.pdf", score=0.7, section="chunk 1"),
                rs.ChatSource(document="two.pdf", score=0.6, section="chunk 0"),
            ],
            ["a0", "a1", "b0"],
            [0.8, 0.7, 0.6],
        ),
    )
    monkeypatch.setattr(
        "app.pipeline.complete",
        lambda q, c, mode="rag": _completion(
            "a grounded answer", 40, 100, "openai/gpt-oss-120b"
        ),
    )
    monkeypatch.setattr(
        "app.pipeline.classify_groundedness",
        lambda score, **k: "High",
    )

    result = rs.run_rag("q", "user-1")

    assert result.answer == "a grounded answer"
    assert result.model == "openai/gpt-oss-120b"
    assert result.tokens_used == 100
    assert result.chunks_retrieved == 3
    assert result.sources[0].document == "one.pdf"
    assert result.retrieval_score == pytest.approx((0.8 + 0.7 + 0.6) / 3)
    assert result.context_chars == len("a0") + len("a1") + len("b0")
    assert result.groundedness == "High"


# ---------------------------------------------------------------------------
# run_stuffed / get_full_document_text
# ---------------------------------------------------------------------------


class _SnapTable:
    """Table stub that records the last insert/select and returns fixed data."""

    def __init__(self, data):
        self._data = data
        self._select = None
        self._insert_rows = None

    def select(self, *cols):
        self._select = cols
        return self

    def in_(self, col, values):
        return self

    def order(self, col):
        return self

    def eq(self, col, val):
        return self

    def insert(self, rows):
        self._insert_rows = rows
        return self

    def execute(self):
        class _R:
            data = self._data
        return _R()


class _StuffedSb:
    """Distinguishes document_chunks from documents by table name."""

    def __init__(self):
        self.chunks = [
            {"document_id": "doc-a", "chunk_index": 0, "content": "a0"},
            {"document_id": "doc-a", "chunk_index": 1, "content": "a1"},
            {"document_id": "doc-b", "chunk_index": 0, "content": "b0"},
        ]
        self.docs = [
            {"id": "doc-a", "filename": "one.pdf"},
            {"id": "doc-b", "filename": "two.pdf"},
        ]

    def table(self, name):
        if name == "document_chunks":
            return _SnapTable(self.chunks)
        return _SnapTable(self.docs)


def test_get_full_document_text_reconstructs_order_by_chunk(monkeypatch):
    monkeypatch.setattr("app.retrieval.get_supabase", lambda: _StuffedSb())

    full, filenames = rs.get_full_document_text("user-1")

    assert "a0" in full and "a1" in full and "b0" in full
    assert "one.pdf" in full and "two.pdf" in full
    assert set(filenames) == {"one.pdf", "two.pdf"}


def test_run_stuffed_uses_full_document_prompt_mode(monkeypatch):
    monkeypatch.setattr("app.pipeline.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.retrieval.get_supabase", lambda: _StuffedSb())

    seen = {}

    def fake_complete(q, c, mode="rag"):
        seen["mode"] = mode
        seen["context"] = c
        return _completion("stuffed answer", 800, 8000, "openai/gpt-oss-120b")

    monkeypatch.setattr("app.pipeline.complete", fake_complete)
    monkeypatch.setattr(
        "app.pipeline.classify_groundedness",
        lambda score, **k: "Medium",
    )

    result = rs.run_stuffed("q", "user-1")

    assert seen["mode"] == "full-document"
    assert result.answer == "stuffed answer"
    assert result.tokens_used == 8000
    assert result.groundedness == "Medium"
    assert result.model == "openai/gpt-oss-120b"
    assert {s.document for s in result.sources} == {"one.pdf", "two.pdf"}
    # No retrieval: there is no similarity to report, and context_chars is the
    # size of the stuffed corpus (headers included).
    assert result.retrieval_score is None
    assert result.context_chars == len(seen["context"][0])


def test_run_stuffed_without_documents_returns_canned(monkeypatch):
    class _EmptySb:
        def table(self, name):
            return _SnapTable([])

    monkeypatch.setattr("app.pipeline.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.retrieval.get_supabase", lambda: _EmptySb())

    result = rs.run_stuffed("q", "user-1")

    assert "no indexed documents" in result.answer.lower()
    assert result.tokens_used == 0
    assert result.sources == []
