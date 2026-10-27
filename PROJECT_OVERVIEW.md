# RagPilot — Project Overview

> **Español:** [PROJECT_OVERVIEW.es.md](PROJECT_OVERVIEW.es.md)

I built RagPilot to answer one question honestly: **does retrieval actually beat
just stuffing the whole document into an LLM prompt?**

It is a demo in two parts: a FastAPI backend that ingests documents, chunks
them, and embeds them into pgvector; and a React workspace where you run two
pipelines on the same question — **RAG** (retrieve the relevant chunks, then
generate) and **full-doc** (generate with the whole corpus crammed into one
prompt, the naive baseline RAG replaces). And then I made the dashboard show the
tradeoff live, in the user's own data.

---

## Why I built this (and why RAG matters)

Most of the questions a company actually asks an LLM are not about what the
model already knows. They are about its own data: product documentation, support
tickets, internal policy, changelogs. A model trained months ago does not have
that knowledge, guesses when it does not, and charges tokens while it guesses.

I kept running into the same three problems whenever someone plugged an LLM into
daily operations or a chatbot:

1. **Frozen knowledge.** The model knows what it was trained on, not what the
   company shipped last week. Every answer about current, private, or
   ever-changing data is a coin flip.
2. **The expensive workaround.** The naive fix is to paste everything into the
   prompt. It works until the document set grows — then every single request
   burns a giant prompt, gets slower, and still answers from the first section
   that looks relevant.
3. **No proof.** You cannot tell which statement came from your data and which
   one the model invented to sound helpful.

RAG is the approach I concluded makes sense: retrieve only the parts of your own
documents that are relevant to the question, and let the model answer from
exactly that evidence. The knowledge stays in your documents — update them and
the answers update with them, no retraining, no model fine-tuning. And because
the answer is built from fetched evidence, it can point back to its source.

I wanted the project to demonstrate that, not assert it. So the contrast is
engineered, but the numbers are real:

- The corpus contains questions with **two plausible answers** buried in
  different sections (e.g. "Which version is more recent by date, v2.4 or
  v2.8?" — the version list is not chronological).
- The questions are written so retrieval reaches the right nuance while reading
  a fraction of the document. The full-doc baseline sees everything and can
  generalize or pick the wrong value, but that outcome varies by model and
  run — the always-measurable contrast is cost and latency.
- Both sides of every comparison are persisted and aggregated, and both
  pipelines share the same model, so the demo isolates **retrieval**, not the
  model.

---

## Architecture

I split the project into three pieces: a thin React client, a single FastAPI
orchestrator, and Supabase for storage and analytics. I decided early that only
the backend would talk to the AI services and the database; the browser just
presents files, comparisons, and results.

**Client (React).** The workspace does three things: signs the user in through
Supabase Auth, sends the selected documents to the backend, and renders each
comparison plus the live dashboard. It never holds more than the user's auth
token and the backend URL.

**Backend (FastAPI).** Every request carries a JWT that `auth.py` validates
server-side; from there the work splits by responsibility:

- **Ingestion** (`documents.py`) takes the multipart upload, enforces the
  24 KB budget, extracts and chunks the text, embeds it, and stores the chunk
  vectors plus the raw file in Storage.
- **The comparison** (`compare.py`) runs both pipelines on the same question
  and persists the outcome — RAG retrieves the top matching chunks and answers
  from them, while the full-doc baseline pulls the entire selected corpus and
  stuffs it into a single prompt. Two LLM calls, same model.
- **The dashboard** (`metrics.py`) reads the persisted rows back and
  aggregates them into the live KPIs, recent queries, and comparison history.
- **Shared plumbing** (`rag_service.py`, `embeddings.py`) carries the
  retrieval → prompt → generate pipeline both sides reuse, plus vector
  normalization before similarity search.

**Data layer (Supabase).** Three pieces keep state: a private Storage bucket
with one folder per user for the original files; Postgres with pgvector holding
the chunk embeddings, searched through the `match_documents` function; and the
analytics tables (`comparisons`, `queries`) that feed the dashboard.

The flow is one-directional: upload → chunk → embed, then question → RAG or
stuffed answer → persist → aggregate.

### The honest baseline

I decided the comparison only makes sense if retrieval is the variable. So
`/v1/compare` makes two LLM calls per question, both with the same Groq model
(`openai/gpt-oss-120b`), and the only difference is how context reaches the
model. RAG retrieves the top matching chunks (default 5), so its tokens scale
with retrieval; the full-doc baseline stuffs the entire selected corpus verbatim
into the prompt, so its tokens scale with corpus size. RAG fails when retrieval
misses the right chunk; the baseline fails by generalizing from an irrelevant
section. Those are the failure modes behind the design; what the dashboard makes
visible and measurable is cost, latency, and groundedness.

### Ingestion pipeline

1. Upload (multipart) → extract text (PDF, TXT, MD, JSON, CSV)
2. Fixed-size chunking (1,000 chars, 150 overlap, sentence/paragraph snapping)
3. Embed with `gemini-embedding-001` (1536 dims, normalized)
4. Store in `document_chunks` with HNSW cosine index
5. `match_documents` (SQL function, granted only to `service_role`) retrieves
   top-k by cosine similarity, scoped by `user_id`

---

## Decisions I'd defend

### Same model on both sides
An honest comparison needs the model out of the equation. Groq
`openai/gpt-oss-120b` powers both pipelines, and the result isolates retrieval.

### Token budget: 24,000 chars (~6K tokens) per document and per corpus
I learned the hard way that the full-doc baseline stuffs *the entire selected
corpus* into one prompt, and Groq throttles at 8,000 tokens per minute — a
corpus bigger than ~6K tokens gets truncated or fails. I enforce the cap in
three places: at upload (`documents.py`), before any LLM call (`compare.py`
fails fast with `422`), and defensively inside `run_stuffed` (`rag_service.py`).
The demo corpus — ~20.8 KB, 30 chunks — fits with margin.

### Groundedness that doesn't cost a fortune
I label answers `High` / `Medium` / `Low` from retrieval similarity against
configurable thresholds (`0.72`/`0.48`). Only the ambiguous middle band runs a
short LLM judge, so most answers are labeled for free.

### Security posture
- The browser **never** holds the service-role key; it only has the user's
  Supabase Auth JWT, which the backend validates server-side.
- Vectors/embeddings are only writeable by the service-role backend. RLS is
  defense-in-depth: inserts into `document_chunks` validate that the chunk's
  `user_id` matches the owning document (`004_chunk_ownership_rls.sql`).
- Storage is a private bucket, one folder per user; delete removes chunks,
  storage objects, and the document row.

### CamelCase contract
The API speaks camelCase (`storagePath`, `documentIds`) via Pydantic aliases so
`app/schemas.py` mirrors `src/lib/types.ts` one-to-one and the frontend never
translates field names.

### Metrics tell the truth
I decided the dashboard "change" badges should only render when a previous
window actually exists (`change: null` hides the badge). An empty history shows
**no fake 0%**.

---

## Try it yourself

```powershell
# Backend — open a terminal in the backend repo (RagBackendProject)
.\.venv\Scripts\python.exe -m scripts.create_bucket
.\.venv\Scripts\python.exe -m scripts.seed <user_email>        # sample metrics
.\.venv\Scripts\python.exe -m scripts.seed_corpus <user_email> # the 30-chunk corpus
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# Frontend — open a second terminal in the sibling repo (RAGProject)
pnpm install
pnpm run dev
```

Sign in, select the seeded document, and try the three ambiguous questions in
the chat. Watch tokens/latency/context/groundedness for RAG vs full-doc in
the answer cards, and the dashboard refresh after each comparison.

Full setup instructions: `README.md` (backend) and `../RAGProject/README.md`
(frontend).

---

## What it took to keep it honest

I did not want to hand over a project that only works on the demo path. I wrote
47 unit tests covering auth, document handling, chunking, the compare budget
and document filtering, the rag_service pipeline, groundedness, and both metric
endpoints — all mocking the Supabase client, so the suite runs without any live
API key. The frontend builds under strict type checking and passes ESLint. And I
went through the codebase more than once to remove dead code and a leftover
charting dependency, because nothing ages a project faster than dead imports
nobody understands.