"""Unit tests for the dashboard metrics endpoint.

Calls metrics.dashboard_metrics directly with a fake Supabase client and a
stubbed window-count helper; no network or real auth involved.
"""

from __future__ import annotations

import pytest

from app.auth import UserContext
from app.routers import metrics


class _Result:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class _Builder:
    def __init__(self, handler, table):
        self._handler = handler
        self._table = table
        self._cols = None
        self._count = None
        self._gte = None

    def select(self, cols, **kwargs):
        self._cols = cols
        self._count = kwargs.get("count")
        return self

    def eq(self, col, val):
        return self

    def gte(self, col, val):
        self._gte = col
        return self

    def lte(self, col, val):
        return self

    def order(self, col, **kwargs):
        return self

    def limit(self, n):
        return self

    def execute(self):
        return self._handler(self)


class _FakeSb:
    def __init__(self, handler):
        self._handler = handler

    def table(self, name):
        return _Builder(self._handler, name)


USER = UserContext(user_id="user-1", email="u@example.com")


def _make_sb(doc_count: int, chunk_count: int, query_count: int, tokens_data: list):
    def handler(b):
        if b._gte is not None:
            return _Result(count=0)
        if b._cols == "tokens_used":
            return _Result(data=tokens_data)
        counts = {"documents": doc_count, "document_chunks": chunk_count, "queries": query_count}
        return _Result(count=counts[b._table])

    return _FakeSb(handler)


@pytest.fixture(autouse=True)
def _window_is_zero(monkeypatch):
    # First call (current window) reports 5, second call (previous window) 0.
    i = 0

    def fake_window(sb, user_id, latest, days):
        nonlocal i
        i += 1
        return 5 if i == 1 else 0

    monkeypatch.setattr("app.routers.metrics._queries_in_window", fake_window)


def test_dashboard_metrics_snapshot_has_no_change(monkeypatch):
    sb = _make_sb(doc_count=3, chunk_count=30, query_count=2, tokens_data=[{"tokens_used": 400}, {"tokens_used": 100}])
    monkeypatch.setattr("app.routers.metrics.get_supabase", lambda: sb)

    result = metrics.dashboard_metrics(USER)

    assert result.documents.value == 3
    assert result.documents.change is None
    assert result.chunks.value == 30
    assert result.chunks.change is None
    assert result.queries.value == 2
    assert result.queries.change is None
    assert result.tokens.value == 500
    assert result.tokens.change is None


def test_dashboard_metrics_change_from_previous_window(monkeypatch):
    sb = _make_sb(doc_count=0, chunk_count=0, query_count=8, tokens_data=[])
    monkeypatch.setattr("app.routers.metrics.get_supabase", lambda: sb)
    # 8 queries in the current window vs 4 in the previous one -> +100%.
    calls = []

    def fake_window(sb, user_id, latest, days):
        calls.append(days)
        return 4 if len(calls) == 2 else 8

    monkeypatch.setattr("app.routers.metrics._queries_in_window", fake_window)

    result = metrics.dashboard_metrics(USER)

    assert result.queries.value == 8
    assert result.queries.change == 100.0
    assert result.tokens.value == 0
    assert result.tokens.change == 100.0
    assert result.documents.change is None