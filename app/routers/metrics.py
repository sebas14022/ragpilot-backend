"""Dashboard metrics built from the user's real data."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..auth import require_user, UserContext
from ..db import get_supabase
from ..schemas import (
    ComparisonMetrics,
    DashboardMetrics,
    MetricValue,
    QueryPoint,
    QuerySeries,
    RecentQuery,
)

router = APIRouter()


@router.get("/metrics/comparisons", response_model=ComparisonMetrics)
def comparison_metrics(user: UserContext = Depends(require_user)) -> ComparisonMetrics:
    """Aggregate the user's saved comparisons.

    Quality is expressed as the share of answers judged fully grounded in their
    own context, which is the only quality signal we persist. Retrieval
    similarity is deliberately not aggregated: the full-document branch never
    retrieves, so averaging the two would be comparing a measurement with a
    blank.
    """
    sb = get_supabase()
    rows = (
        sb.table("comparisons")
        .select(
            "rag_latency_ms, baseline_latency_ms, rag_tokens_used, "
            "baseline_tokens_used, rag_groundedness, baseline_groundedness"
        )
        .eq("user_id", user.user_id)
        .execute()
    )
    data = rows.data or []

    total = len(data)
    rag_lat_tot = baseline_lat_tot = 0
    tokens = 0
    for r in data:
        rag_lat_tot += int(r.get("rag_latency_ms") or 0)
        baseline_lat_tot += int(r.get("baseline_latency_ms") or 0)
        tokens += int(r.get("rag_tokens_used") or 0) + int(r.get("baseline_tokens_used") or 0)

    def avg_int(val: int, cnt: int) -> int:
        return round(val / cnt) if cnt else 0

    def grounded_rate(column: str) -> float:
        if not total:
            return 0.0
        grounded = sum(1 for r in data if (r.get(column) or "").lower() == "high")
        return round(grounded / total * 100, 1)

    return ComparisonMetrics(
        total=total,
        avgRagLatencyMs=avg_int(rag_lat_tot, total),
        avgBaselineLatencyMs=avg_int(baseline_lat_tot, total),
        tokensUsed=tokens,
        ragGroundedRate=grounded_rate("rag_groundedness"),
        baselineGroundedRate=grounded_rate("baseline_groundedness"),
    )


@router.get("/metrics/dashboard", response_model=DashboardMetrics)
def dashboard_metrics(user: UserContext = Depends(require_user)) -> DashboardMetrics:
    sb = get_supabase()

    def count(table: str) -> int:
        res = sb.table(table).select("id", count="exact").eq("user_id", user.user_id).execute()
        return int((res.count or 0))

    docs = count("documents")
    chunks = count("document_chunks")
    queries = count("queries")

    tokens_res = (
        sb.table("queries")
        .select("tokens_used")
        .eq("user_id", user.user_id)
        .execute()
    )
    tokens = sum(int(r.get("tokens_used") or 0) for r in (tokens_res.data or []))

    # Rough change: queries in the last 30 days vs the 30 before that.
    now = datetime.now(timezone.utc)
    q_cur = _queries_in_window(sb, user.user_id, latest=now, days=30)
    q_prev = _queries_in_window(sb, user.user_id, latest=now - _td(30), days=30)

    def pct(curr: int, prev: int) -> float:
        if prev == 0:
            return 0.0
        return round(((curr - prev) / prev) * 100, 1)

    def metric(value: int, window_cur: int, window_prev: int) -> MetricValue:
        # change is None when there is no previous window to compare against
        # (snapshots like documents/chunks, or a fresh history with no prior
        # period), so the UI can hide the badge instead of showing a fake 0%.
        change = pct(window_cur, window_prev) if window_prev > 0 else None
        return MetricValue(value=value, change=change)

    return DashboardMetrics(
        documents=metric(docs, docs, 0),
        chunks=metric(chunks, chunks, 0),
        queries=metric(queries, q_cur, q_prev),
        tokens=metric(tokens, q_cur, q_prev),
    )


@router.get("/metrics/query-series", response_model=QuerySeries)
def query_series(user: UserContext = Depends(require_user)) -> QuerySeries:
    sb = get_supabase()
    rows = (
        sb.table("queries")
        .select("created_at, chunks_retrieved")
        .eq("user_id", user.user_id)
        .execute()
    )
    data = rows.data or []

    buckets: dict[str, dict] = {}
    for r in data:
        ts = r.get("created_at")
        if not ts:
            continue
        try:
            month = datetime.fromisoformat((ts or "").replace("Z", "+00:00")).strftime("%Y-%m")
        except Exception:
            continue
        b = buckets.setdefault(month, {"queries": 0, "chunks": 0})
        b["queries"] += 1
        b["chunks"] += int(r.get("chunks_retrieved") or 0)

    points = [
        QueryPoint(month=m, queries=b["queries"], chunksRetrieved=b["chunks"])
        for m, b in sorted(buckets.items())
    ]
    return QuerySeries(points=points)


@router.get("/metrics/recent-queries", response_model=list[RecentQuery])
def recent_queries(user: UserContext = Depends(require_user)) -> list[RecentQuery]:
    sb = get_supabase()
    rows = (
        sb.table("queries")
        .select("id, question, created_at, latency_ms, groundedness, status")
        .eq("user_id", user.user_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    result: list[RecentQuery] = []
    for r in (rows.data or []):
        status = r.get("status")
        result.append(
            RecentQuery(
                id=r["id"],
                question=r.get("question") or "",
                timestamp=r.get("created_at"),
                latencyMs=int(r.get("latency_ms") or 0),
                groundedness=r.get("groundedness") or "Low",
                status=status if status in ("success", "failed") else "success",
            )
        )
    return result


def _queries_in_window(sb, user_id: str, latest: datetime, days: int) -> int:
    from datetime import timedelta

    start = (latest - timedelta(days=days)).isoformat()
    res = (
        sb.table("queries")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("created_at", start)
        .lte("created_at", latest.isoformat())
        .execute()
    )
    return int(res.count or 0)


def _td(days: int):
    from datetime import timedelta

    return timedelta(days=days)
