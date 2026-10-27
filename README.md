# RagPilot Backend

> **Español:** [README.es.md](README.es.md)

I built this backend for RagPilot to demonstrate, with real numbers, why
Retrieval-Augmented Generation beats the naive alternative for everyday
operations and chatbots. It ingests user documents into **Supabase pgvector**
with Gemini embeddings, and generates answers through **Groq** (with a
**Gemini** fallback).

The `/compare` endpoint is the heart of it: for the same question it runs RAG
(retrieve only the relevant chunks) against a "full-doc" baseline that stuffs
the entire corpus into a single prompt. I concluded the honest way to compare
them is keeping the same model on both sides, so the only variable is whether
the context was retrieved or stuffed. The token, latency, and groundedness
contrast is visible in the UI and aggregated in the dashboard.

For the full story — why RAG matters, the architecture, and the decisions I
made — read [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md).

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI (async) + Uvicorn |
| Vector store | Supabase Postgres + `pgvector` (cosine, HNSW) |
| Storage | Supabase Storage (private bucket per user) |
| Auth | Supabase Auth (JWT ES256, validated server-side) |
| Embeddings | `gemini-embedding-001` (1536 dims, normalized) |
| LLM | Groq `openai/gpt-oss-120b` (primary), Gemini (fallback) |
| Frontend contract | camelCase via Pydantic aliases |

## Architecture

```
app/
  main.py            FastAPI app, CORS, router mounting (/v1)
  config.py          Pydantic settings from env / .env
  auth.py            JWT dependency -> 401 or UserContext
  db.py              shared Supabase service-role client
  schemas.py         Pydantic request/response models (camelCase aliases)
  routers/
    health.py        GET /v1/health
    documents.py     upload / list / delete documents
    rag.py           POST /v1/rag/query
    compare.py       POST /v1/compare (RAG vs full-doc baseline)
    metrics.py       dashboard KPIs, query series, recent queries
  rag_service.py     shared pipeline: retrieve -> prompt -> generate (+ run_stuffed)
  embeddings.py      Gemini embedding client (normalization)
  chunking.py        fixed-size chunking with overlap + boundary snapping
  text_extraction.py PDF / TXT / MD / JSON / CSV -> plain text
  groundedness.py    heuristic + optional LLM hybrid label
scripts/
  create_bucket.py   create the private Storage bucket
  seed.py            seed sample query metrics for a user
  seed_corpus.py     index the single large demo document for a user
migrations/
  000_full.sql       one-shot full setup (schema + RLS + search + storage)
  001_init.sql       schema, RLS, match_documents
  002_storage.sql    storage bucket + owner policies
  003_comparison_metrics.sql  latency columns on comparisons
  004_chunk_ownership_rls.sql  defense-in-depth RLS on document_chunks
  005_drop_legacy_precision.sql  drops the retired "precision" columns
tests/               pytest suite (auth, documents, chunking, compare, rag_service,
                     groundedness, prompt, metrics)
```

The backend authenticates to Supabase with the **service_role** key so it can
bypass RLS and manage vectors/storage on behalf of any user. The browser is
never given this key — it only ever holds the user's Supabase Auth access token.

## Setup

1. Clone and create a virtual environment.

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```

2. Create `.env` from the example and fill in real values.

   ```powershell
   Copy-Item .env.example .env
   ```

   Required variables (see `app/config.py` for defaults):

   | Variable | Purpose |
   |---|---|
   | `SUPABASE_URL` | your Supabase project URL |
   | `SUPABASE_SERVICE_ROLE_KEY` | server-side key (never exposed) |
   | `SUPABASE_JWT_SECRET` | HS256 secret used to validate user JWTs |
   | `GEMINI_API_KEY` | Google AI Studio API key (embeddings + LLM fallback) |
   | `GEMINI_MODEL` | fallback LLM model |
   | `GEMINI_EMBEDDING_MODEL` | embedding model, default `gemini-embedding-001` |
   | `EMBEDDING_DIM` | vector dimensionality, default `1536` (must match schema) |
   | `GROQ_API_KEY` | Groq API key (primary LLM) |
   | `GROQ_MODEL` | primary LLM model, default `openai/gpt-oss-120b` |
   | `MAX_DOCUMENT_CHARS` | per-document / per-corpus budget, default `24000` (~6K tokens) |

3. Apply the database schema.

   Paste `migrations/000_full.sql` into the Supabase SQL Editor and Run (or
   `supabase db push`). This creates the tables, the RLS policies, the
   `match_documents` function, and the storage bucket. No other migration files
   are needed for a fresh setup.

4. Create the Storage bucket (idempotent).

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.create_bucket
   ```

5. Run the server.

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

   Interactive docs at http://localhost:8000/docs.

## Endpoints (all under `/v1`)

Authenticated endpoints require `Authorization: Bearer <access_token>` where the
token is issued by Supabase Auth for the logged-in user.

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/v1/health` | liveness probe | No |
| POST | `/v1/documents` | upload a document (multipart) | Yes |
| GET | `/v1/documents` | list the user's documents | Yes |
| POST | `/v1/documents/{doc_id}/delete` | delete a document + its chunks | Yes |
| POST | `/v1/rag/query` | ask a question over context | Yes |
| POST | `/v1/compare` | RAG answer vs no-context baseline | Yes |
| GET | `/v1/metrics/dashboard` | KPIs (documents, chunks, queries, tokens) | Yes |
| GET | `/v1/metrics/query-series` | monthly query/chunks series | Yes |
| GET | `/v1/metrics/recent-queries` | last 20 queries | Yes |

### `/v1/rag/query`

```json
{
  "question": "What does the onboarding policy say about remote work?",
  "documentIds": []   // optional; restrict retrieval to these documents
}
```

When `documentIds` is provided and non-empty, retrieval is limited to those
documents. If omitted, all of the user's indexed documents are searched.

Response (`ChatResponse`):

```json
{
  "answer": "...",
  "model": "openai/gpt-oss-120b",
  "latencyMs": 1812,
  "groundedness": "High",
  "tokensUsed": 235,
  "sources": [{ "document": "policy.pdf", "section": "chunk 3", "score": 0.83 }]
}
```

### `/v1/compare`

Runs the RAG pipeline against a **full-doc baseline**. RAG retrieves only the
relevant chunks and injects them as context; the baseline uses `run_stuffed` to
shove the entire selected document corpus into a single prompt (the anti-pattern
RAG replaces). Each request performs **two** LLM calls and reports latency,
tokens, context usage, and groundedness for both sides. Both branches are scored
the same way: retrieval similarity when there was retrieval, and a short
content-based check otherwise.

```json
{
  "query": "Which version was released more recently by date, v2.4 or v2.8?",
  "documentIds": ["<doc-uuid>"]   // optional; restrict retrieval/corpus to these
}
```

When `documentIds` is provided and non-empty, both pipelines are limited to
those documents. If omitted, the user's whole corpus is used. Because the
baseline stuffs the whole selection into one prompt, the total selected corpus
must stay under `MAX_DOCUMENT_CHARS` (24,000 chars) — the endpoint returns
`422` before running anything if the selection exceeds it. The corpus size is
measured on the reconstructed text, so chunk overlap is never counted twice.

## Supported document formats

- PDF (`.pdf`) — text extraction via `pypdf`
- Plain text / Markdown (`.txt`, `.md`)
- JSON (`.json`) — pretty-printed
- CSV (`.csv`) — pipe-joined rows

## Groundedness

Answers are labeled `High` / `Medium` / `Low` using a **hybrid** strategy:

- If retrieval similarity is clearly above/below the thresholds (`0.72` high /
  `0.48` medium by default), the label is derived from the score — no extra LLM cost.
- Only in the ambiguous `Medium` band does it run a short LLM check
  (`GROUNDEDNESS_LLM_FALLBACK=true` by default) that judges whether the answer is
  actually supported by the context.
- The full-doc baseline has no retrieval score, so it always takes the content
  path: the same LLM check judges whether the answer is supported by the stuffed
  corpus. Scoring it any other way would make RAG win by construction.

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Coverage (unit tests, no live API calls): auth, documents (upload/list/delete),
chunking, compare budget + document filtering, rag_service retrieval/prompts,
groundedness, comparison metrics, dashboard metrics.

## Seeding sample metrics

```powershell
.\.venv\Scripts\python.exe -m scripts.seed <user_email>
```

Inserts generated query rows for a user so the dashboard has data to show.

## Seeding the demo corpus

The single file `docs/sample_document_large.md` holds a fictional RagPilot
knowledge base: **~20.8 KB / ~5.2K tokens / 30 chunks**. It is a single file on
purpose: the RAG-vs-full-doc contrast (Part 23 of the doc) depends on a large
document with many sections. It is deliberately written so several questions
have answers that are easy to get wrong with the whole document stuffed into one
prompt (e.g. "Which version is more recent by date, v2.4 or v2.8?" — the list is
not chronological). Index it for a user so the contrast is meaningful:

```powershell
.\.venv\Scripts\python.exe -m scripts.seed_corpus <user_email>
```

This chunks, embeds, and indexes the single file with the real pipeline functions
using the service-role client. Select the resulting document in the UI before
running comparisons.
