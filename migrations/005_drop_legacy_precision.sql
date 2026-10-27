-- RagPilot — retire the legacy "precision" columns from public.comparisons.
--
-- 003_comparison_metrics.sql added rag_precision/baseline_precision as if they
-- measured answer quality. They did not:
--   * rag_precision stored the average cosine similarity of the retrieved
--     chunks (x100), which says nothing about whether the answer is right;
--   * baseline_precision was hardcoded to 0.0, because the full-document
--     branch never retrieves, so every row carried a fake zero.
--
-- Nothing reads or writes these columns anymore. Retrieval similarity is
-- returned per comparison as context.avgSimilarity, and answer quality is
-- tracked through the groundedness labels that were already being persisted.
--
-- Apply in the Supabase SQL Editor (idempotent).

alter table public.comparisons
  drop column if exists rag_precision,
  drop column if exists baseline_precision;
