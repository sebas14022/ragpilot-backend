-- RagPilot — comparison analytics columns.
-- Adds per-precision (0–100) columns to public.comparisons so the RAG vs
-- baseline analytics can be aggregated historically from the persisted rows.
-- Apply in the Supabase SQL Editor (idempotent).

alter table public.comparisons
  add column if not exists rag_precision float,
  add column if not exists baseline_precision float;
