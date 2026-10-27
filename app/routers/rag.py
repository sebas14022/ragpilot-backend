"""RAG query endpoint: retrieve -> prompt -> generate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_user, UserContext
from ..config import get_settings
from ..db import get_supabase
from ..rag_service import run_rag
from ..schemas import ChatResponse, RagQueryInput

router = APIRouter()


@router.post("/rag/query", response_model=ChatResponse)
def run_query(payload: RagQueryInput, user: UserContext = Depends(require_user)) -> ChatResponse:
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    settings = get_settings()
    result = run_rag(question, user.user_id, document_ids=payload.documentIds)

    # Persist the query with real metrics.
    get_supabase().table("queries").insert(
        {
            "user_id": user.user_id,
            "question": question,
            "answer": result.answer,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "groundedness": result.groundedness,
            "tokens_used": result.tokens_used,
            "chunks_retrieved": result.chunks_retrieved,
        }
    ).execute()

    return ChatResponse(
        answer=result.answer,
        model=result.model,
        latencyMs=result.latency_ms,
        groundedness=result.groundedness,
        tokensUsed=result.tokens_used,
        sources=result.sources,
    )
