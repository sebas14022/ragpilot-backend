"""RagPilot FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import compare, documents, health, metrics, rag

settings = get_settings()

app = FastAPI(
    title="RagPilot Backend",
    version="0.1.0",
    description="RAG orchestrator: Supabase pgvector + Gemini embeddings/LLM",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/v1", tags=["health"])
app.include_router(documents.router, prefix="/v1", tags=["documents"])
app.include_router(rag.router, prefix="/v1", tags=["rag"])
app.include_router(compare.router, prefix="/v1", tags=["compare"])
app.include_router(metrics.router, prefix="/v1", tags=["metrics"])
