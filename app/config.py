from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_jwt_secret: str
    supabase_anon_key: str = ""

    # Google Gemini (embeddings + fallback LLM)
    gemini_api_key: str
    gemini_model: str = "gemini-3.6-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 1536

    # Groq (primary LLM generation)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    # Document budget: the full-doc baseline stuffs the WHOLE selected corpus
    # into a single prompt, so every document (and the sum of the selected ones)
    # must stay under the LLM request token limit (~6K tokens ≈ 24K chars).
    max_document_chars: int = 24000

    # RAG behaviour
    rag_top_k: int = 5
    rag_min_score: float = 0.25
    grounded_high: float = 0.72
    grounded_medium: float = 0.48
    groundedness_llm_fallback: bool = True

    # CORS
    cors_origins: str = "http://localhost:5173"

    # Storage
    storage_bucket: str = "ragpilot-docs"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
