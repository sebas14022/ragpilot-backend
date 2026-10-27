"""Unit tests for the compare endpoint's document_ids forwarding.

Calls the compare router via a fake Supabase client and mocked RAG pipelines;
no network or real auth involved.
"""

from __future__ import annotations

import pytest

from app.auth import UserContext
from app.routers import compare
from app.schemas import ChatSource


class _Result:
    def __init__(self, data=None):
        self.data = data


class _Builder:
    def __init__(self, sb):
        self._sb = sb

    def insert(self, rows):
        self._rows = rows
        return self

    def execute(self):
        return _Result([self._rows])


class _FakeSb:
    def table(self, name):
        return _Builder(self)


USER = UserContext(user_id="user-1", email="u@example.com")


class _Settings:
    gemini_model = "gemini-3.6-flash"
    groq_api_key = ""
    groq_model = "openai/gpt-oss-120b"
    max_document_chars = 24000


def _result(answer, model, latency, groundedness, tokens, sources, retrieval_score, chunks, context_chars):
    return type(
        "RagResult",
        (),
        {
            "answer": answer,
            "model": model,
            "latency_ms": latency,
            "groundedness": groundedness,
            "tokens_used": tokens,
            "sources": sources,
            "retrieval_score": retrieval_score,
            "context_chars": context_chars,
            "chunks_retrieved": chunks,
        },
    )()


def _source(document, *, score=None, section=None):
    return ChatSource(document=document, score=score, section=section)


def _patched(stage, captured, which):
    def _run(question, user_id, document_ids=None):
        s = {"stage": stage, "question": question, "user_id": user_id, "document_ids": document_ids}
        captured[which] = s
        if which == "rag":
            return _result(
                "rag answer", "gemini-3.6-flash", 100, "High", 50,
                [_source("doc-a"), _source("doc-a")], 0.8, 2, 1200,
            )
        return _result(
            "stuffed answer", "openai/gpt-oss-120b", 800, "Medium", 8000,
            [_source("doc-a")], None, 0, 9000,
        )
    return _run


def _patch(monkeypatch, captured):
    monkeypatch.setattr("app.routers.compare.get_supabase", lambda: _FakeSb())
    monkeypatch.setattr(
        "app.routers.compare.corpus_char_count",
        lambda user_id, document_ids=None: 10,
    )
    monkeypatch.setattr("app.routers.compare.run_rag", _patched("rag", captured, "rag"))
    monkeypatch.setattr("app.routers.compare.run_stuffed", _patched("stuffed", captured, "baseline"))


def test_compare_forwards_document_ids(monkeypatch):
    captured = {}
    _patch(monkeypatch, captured)

    payload = compare.CompareInput(query="what is revenue?", documentIds=["doc-a", "doc-b"])
    result = compare.compare(payload, USER)

    assert captured["rag"]["question"] == "what is revenue?"
    assert captured["rag"]["user_id"] == "user-1"
    assert captured["rag"]["document_ids"] == ["doc-a", "doc-b"]
    assert captured["baseline"]["question"] == "what is revenue?"
    assert captured["baseline"]["document_ids"] == ["doc-a", "doc-b"]
    assert result.query == "what is revenue?"
    assert result.rag.answer == "rag answer"
    assert result.baseline.answer == "stuffed answer"
    assert result.rag.tokens_used == 50
    assert result.baseline.tokens_used == 8000

    # Context usage is reported per branch instead of a single fake "precision".
    assert result.rag.context.kind == "retrieval"
    assert result.rag.context.chunks == 2
    assert result.rag.context.documents == 1  # both chunks come from doc-a
    assert result.rag.context.characters == 1200
    assert result.rag.context.avg_similarity == 0.8

    assert result.baseline.context.kind == "full-document"
    assert result.baseline.context.chunks == 0
    assert result.baseline.context.documents == 1
    assert result.baseline.context.characters == 9000
    assert result.baseline.context.avg_similarity is None


def test_compare_document_ids_none_defaults(monkeypatch):
    captured = {}
    _patch(monkeypatch, captured)

    payload = compare.CompareInput(query="hello")
    compare.compare(payload, USER)

    assert captured["rag"]["document_ids"] is None
    assert captured["baseline"]["document_ids"] is None


def test_compare_requires_query(monkeypatch):
    _patch(monkeypatch, {})

    with pytest.raises(Exception):
        compare.compare(compare.CompareInput(query="   "), USER)


def test_compare_raises_422_when_corpus_exceeds_budget(monkeypatch):
    from fastapi import HTTPException

    captured = {}
    _patch(monkeypatch, captured)
    monkeypatch.setattr(
        "app.routers.compare.corpus_char_count",
        lambda user_id, document_ids=None: 999999,
    )
    monkeypatch.setattr("app.routers.compare.get_settings", lambda: _Settings())

    payload = compare.CompareInput(query="q", documentIds=["doc-a", "doc-b"])
    with pytest.raises(HTTPException) as exc:
        compare.compare(payload, USER)
    assert exc.value.status_code == 422
    assert "character budget" in exc.value.detail
    assert "rag" not in captured and "baseline" not in captured
