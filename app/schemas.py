"""Pydantic response/request models matching src/lib/types.ts on the frontend.

Types are inline here (not auto-generated) so the backend is decoupled from the
frontend repo. Field names/order intentionally mirror the TS interfaces.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Groundedness = Literal["High", "Medium", "Low"]
DocumentStatus = Literal["indexed", "processing", "failed"]


class DocumentSummary(BaseModel):
    id: str
    filename: str
    status: DocumentStatus
    chunks: int
    createdAt: datetime
    storage_path: str | None = Field(default=None, alias="storagePath")

    model_config = {"populate_by_name": True}


class DocumentList(BaseModel):
    documents: list[DocumentSummary]
    total: int


class UploadResult(BaseModel):
    id: str
    filename: str
    status: DocumentStatus
    chunks: int = 0


class ChatSource(BaseModel):
    document: str
    page: int | None = None
    section: str | None = None
    # None when the branch did not retrieve (full-document baseline): the whole
    # file was used, so there is no per-chunk similarity to report.
    score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    model: str
    latency_ms: int = Field(alias="latencyMs")
    groundedness: Groundedness
    tokens_used: int = Field(alias="tokensUsed")
    sources: list[ChatSource]

    model_config = {"populate_by_name": True}


class RagQueryInput(BaseModel):
    question: str
    documentIds: list[str] | None = None


class ContextUsage(BaseModel):
    """How much material each branch fed the model.

    ``retrieval`` reports the retrieved chunks and their average similarity;
    ``full-document`` reports how many whole files were stuffed and how big they
    were. Keeping this explicit avoids pretending the branches share a score.
    """

    kind: Literal["retrieval", "full-document"]
    chunks: int = 0
    documents: int = 0
    characters: int = 0
    avg_similarity: float | None = Field(default=None, alias="avgSimilarity")

    model_config = {"populate_by_name": True}


class ComparisonAnswer(BaseModel):
    label: str
    model: str
    latency_ms: int = Field(alias="latencyMs")
    groundedness: Groundedness
    tokens_used: int = Field(alias="tokensUsed")
    context: ContextUsage
    sources: list[ChatSource]
    answer: str

    model_config = {"populate_by_name": True}


class ComparisonResult(BaseModel):
    query: str
    rag: ComparisonAnswer
    baseline: ComparisonAnswer


class MetricValue(BaseModel):
    value: int
    change: float | None = 0.0


class DashboardMetrics(BaseModel):
    documents: MetricValue
    chunks: MetricValue
    queries: MetricValue
    tokens: MetricValue


class QueryPoint(BaseModel):
    month: str
    queries: int
    chunksRetrieved: int = Field(alias="chunksRetrieved")

    model_config = {"populate_by_name": True}


class QuerySeries(BaseModel):
    points: list[QueryPoint]


class RecentQuery(BaseModel):
    id: str
    question: str
    timestamp: datetime
    latencyMs: int = Field(alias="latencyMs")
    groundedness: Groundedness
    status: Literal["success", "failed"]

    model_config = {"populate_by_name": True}


class ComparisonMetrics(BaseModel):
    """Aggregates over the user's saved comparisons.

    There is no "precision": without ground-truth answers the only honest
    quality signal we can persist is how often each branch produced an answer
    fully supported by its context.
    """

    total: int
    avg_rag_latency_ms: int = Field(alias="avgRagLatencyMs")
    avg_baseline_latency_ms: int = Field(alias="avgBaselineLatencyMs")
    tokens_used: int = Field(alias="tokensUsed")
    rag_grounded_rate: float = Field(alias="ragGroundedRate")
    baseline_grounded_rate: float = Field(alias="baselineGroundedRate")

    model_config = {"populate_by_name": True}
