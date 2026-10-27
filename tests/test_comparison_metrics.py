"""Unit tests for the comparison metrics endpoint.

Calls metrics.comparison_metrics directly with a fake Supabase client; no
network or real auth involved.
"""

from __future__ import annotations

from app.auth import UserContext
from app.routers import metrics


class _Result:
    def __init__(self, data=None):
        self.data = data


class _Builder:
    def __init__(self, sb, rows):
        self._sb = sb
        self._rows = rows

    def select(self, cols):
        self.ops = []
        self.ops.append(("select", cols))
        return self

    def eq(self, col, val):
        self.ops.append(("eq", col, val))
        return self

    def execute(self):
        return _Result(self._rows)


class _FakeSb:
    def __init__(self, rows):
        self._rows = rows

    def table(self, name):
        return _Builder(self, self._rows)


USER = UserContext(user_id="user-1", email="u@example.com")


def test_comparison_metrics_aggregates_user_rows(monkeypatch):
    rows = [
        {
            "rag_latency_ms": 120,
            "baseline_latency_ms": 80,
            "rag_tokens_used": 500,
            "baseline_tokens_used": 300,
            "rag_groundedness": "High",
            "baseline_groundedness": "Low",
        },
        {
            "rag_latency_ms": 200,
            "baseline_latency_ms": 90,
            "rag_tokens_used": 600,
            "baseline_tokens_used": 250,
            "rag_groundedness": "High",
            "baseline_groundedness": "Medium",
        },
    ]
    fake = _FakeSb(rows)
    monkeypatch.setattr("app.routers.metrics.get_supabase", lambda: fake)

    result = metrics.comparison_metrics(USER)

    assert result.total == 2
    assert result.avg_rag_latency_ms == 160
    assert result.avg_baseline_latency_ms == 85
    assert result.tokens_used == 500 + 300 + 600 + 250  # 1650
    assert result.rag_grounded_rate == 100.0
    assert result.baseline_grounded_rate == 0.0


def test_grounded_rate_counts_only_fully_grounded_answers(monkeypatch):
    rows = [
        {"rag_groundedness": "High", "baseline_groundedness": "Medium"},
        {"rag_groundedness": "Medium", "baseline_groundedness": "Low"},
        {"rag_groundedness": "Low", "baseline_groundedness": "high"},
        {"rag_groundedness": None, "baseline_groundedness": "High"},
    ]
    fake = _FakeSb(rows)
    monkeypatch.setattr("app.routers.metrics.get_supabase", lambda: fake)

    result = metrics.comparison_metrics(USER)

    assert result.rag_grounded_rate == 25.0  # 1 of 4
    assert result.baseline_grounded_rate == 50.0  # 2 of 4, "high" included


def test_comparison_metrics_empty(monkeypatch):
    fake = _FakeSb([])
    monkeypatch.setattr("app.routers.metrics.get_supabase", lambda: fake)

    result = metrics.comparison_metrics(USER)

    assert result.total == 0
    assert result.avg_rag_latency_ms == 0
    assert result.avg_baseline_latency_ms == 0
    assert result.tokens_used == 0
    assert result.rag_grounded_rate == 0.0
    assert result.baseline_grounded_rate == 0.0
