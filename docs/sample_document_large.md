# RagPilot — Complete Company & Product Knowledge Base

Single comprehensive reference for RagPilot, a fictitious B2B SaaS platform used
to demonstrate retrieval-augmented generation (RAG). This one large document
is exactly the RAG scenario: retrieve only the relevant section rather than read
the whole file. The "full-document" baseline reads all of it on every query.

---

# Part 1 — Company & Product Overview

RagPilot is a B2B SaaS platform that helps teams build retrieval-augmented
generation applications on their own document stores, with managed indexing,
embeddings, and query APIs under per-tenant isolation. Founded 2023,
headquartered in Austin, Texas, remote-first.

Co-founders: **Andrea Villanueva** (CEO) and **Marcus Chen** (CTO). Series A
closed **October 2024** at a **$240M** valuation, led by Meridian Ventures.

- v1.0 — May 2023. Initial launch.
- v2.0 — Feb 2025. Managed embeddings API, project namespaces.
- v2.4 — Jun 2025. Similarity threshold, JSON/CSV support, metrics dashboard.
- v2.8 — Mar 4 2025. Per-tenant isolation hardening and SSO.

FY2025 revenue: **$12.4M** (up 58% from $7.8M in 2024). ARR grew $6.2M → $11.9M.
NRR 118%. 68% of new customers started as self-serve trials. 1,284 paying
customers at year-end.

---

# Part 2 — Pricing, Plans & Billing

| Tier | Monthly | Annual (per month, billed yearly) | Projects | Vector ops / month | Extras |
|------|---------|-----------------------------------|----------|--------------------|--------|
| Sandbox | $0 | $0 | 1 | 100K | Trial only; no SLA |
| Starter | $49 | $39.20 | 3 | 1M | Community support |
| Pro | $249 | $199.20 | Unlimited | 10M | Priority email, SSO |
| Enterprise | Custom | Custom | Unlimited | Unlimited | VPC peering, 99.9% SLA |

- A vector operation = any request that reads/writes/scores an embedding index
  (indexing a chunk, a query, re-scoring). Metadata-only and deletes are free.
- Overages: Starter/Pro stop indexing once allowance exhausted. Raise the cap in
  billing (prorated). **Overage = $2 per additional 100K vector operations**.
- Sandbox: 14-day trial of Pro limits, starting at first upload.
- Refund: annual = full refund in first 30 days, then prorated quarterly;
  monthly = non-refundable beyond current period. Refunds processed in 5 business
  days. Sandbox exempt from the 30-day window.
- Invoicing: monthly on the 1st; annual on renewal; Enterprise supports POs, net-30.
- Upgrade: immediate + prorated. Downgrade: at renewal; oversized index becomes read-only.

---

# Part 3 — API Reference

- Base URL: `https://api.ragpilot.io`, stable version `/v1`.
- Auth: `Authorization: Bearer <token>`. Server tokens (OAuth2 scopes) + user
  JWTs (OAuth2 flow). Tokens expire after 1 hour; refresh tokens after 14 days.
- Rate limits (per token): indexing 100/min, queries 300/min, project mgmt
  60/min, read-only metadata 500/min.
- Pagination: `?cursor=` from `next_cursor`; page capped at 200; cursor valid 10 min.
- Errors: `{error:{code,message,details}}`. Codes: unauthorized, invalid_request,
  not_found, rate_limit_exceeded, quota_exceeded, service_unavailable.
- Scopes: read:projects, write:projects, write:documents, read:queries, query:execute.
- Endpoints:
  - `GET/POST /projects`, `DELETE /projects/{id}`
  - `POST /documents` (PDF, TXT, MD, JSON, CSV), `GET /documents/{id}`, `DELETE /documents/{id}`
  - `POST /queries` `{query, project_id, top_k}` (default top_k 5), `GET /queries`

---

# Part 4 — Security, Encryption & Isolation

- Multi-tenant isolation at 3 layers: per-tenant index namespace, chunk/doc
  tenant identifier, and unique API keys + storage prefixes.
- Encryption: AES-256 at rest (documents + embeddings), TLS 1.2+ in transit,
  keys rotated quarterly.
- Access: short-lived signed tokens (1h), ES256 with rotatable JWKS. RBAC on every request.
- Audit logs: 90 days, append-only, exportable.
- RagPilot does **not** train foundation models on customer data.
- Enterprise: VPC peering; P1 incidents communicated within 24h, post-mortem in 7 days.

---

# Part 5 — Data Retention & Purge

- Raw files: free/Sandbox auto-deleted after 90 days; paid retained for project life.
- Chunks + embeddings: retained for project life.
- Query & audit logs: 90 days.
- Project deletion: immediate purge; 14-day soft-delete grace period, then permanent.
- Document deletion: removes chunks/embeddings immediately; raw file purged in 24h.
- Export: chunks + embeddings via API as JSON; not billed as vector ops.
- Enterprise: configurable retention locking.

---

# Part 6 — Compliance & Certifications

| Framework | Status | Notes |
|-----------|--------|-------|
| SOC 2 Type II | Certified | Security, availability, confidentiality |
| ISO 27001 | In progress | Target end of 2026 |
| GDPR | Compliant | DPA, EU residency |
| CCPA/CPRA | Compliant | No sale of personal info |
| HIPAA BAA | Available | Enterprise only |

- Regions: `us-east-1`, `us-west-2`, `eu-central-1`. Chosen at creation; not changeable.
- Sub-processor list in trust portal, updated within 10 days.

---

# Part 7 — Product Roadmap 2026

- Q1: Hybrid search GA, reranker API, dashboard metrics GA.
- Q2: Multi-region indexes, document versioning, batch import SDK.
- Q3: Hierarchical collections, query explanation panel, custom embedding endpoints (Enterprise).
- Q4: Hybrid semantic + metadata filters, **on-prem / single-tenant deployment**, index health checks.
- Longer: multimodal support, agentic tool-calling tier.

---

# Part 8 — Release Notes

- v1.0 May 2023; v2.0 Feb 2025; v2.4 Jun 2025; v2.8 Mar 4 2025 (note: version
  numbers reflect product line, not strict chronology).
- v2.8: per-tenant isolation hardening, SSO (SAML/OIDC), exportable 90-day audit
  logs, query groundedness. v3.0 planned: hybrid search, reranker, multi-region.
- v2.8 requires ES256 tokens; legacy HS256 rejected. Update SDKs to >= 2025-03-04.
- `v1` API stays backward compatible; deprecations announced 6 months ahead;
  no breaking changes v2.0→v2.8.

---

# Part 9 — Embedding Models & Dimensions

| Model | Dimensions | Notes |
|-------|-----------|-------|
| `ragpilot-embed-001` | **1536** | Default. Balanced quality/speed. |
| `ragpilot-embed-compact` | **768** | Smaller index, lower storage cost. |
| `ragpilot-embed-max` | **3072** | Highest quality, larger index. |

- Default model: `ragpilot-embed-001` at **1536 dimensions**.
- 1536 = general purpose; 768 = when storage cost/index footprint dominates;
  3072 = high-stakes quality where size/latency are acceptable tradeoffs.
- Model is set per project at creation and **cannot be changed later**. Changing
  requires a new project + re-upload (batch import SDK streamlines).

---

# Part 10 — Vector Index Sizing & Performance

| Tier | Max vectors | Practical scale |
|------|-------------|-----------------|
| Sandbox | 100K | Prototyping |
| Starter | 1M | Small teams |
| Pro | Unlimited | Tens of millions |
| Enterprise | Unlimited | Very large corpora |

- Estimate vectors as `total_chars / 800`. A 40MB corpus ≈ 50K chunks.
- Target: **p95 end-to-end latency < 1.2s** for indexes up to 10M vectors at top_k 5.
  Tracked with Prometheus; alert fires if p95 exceeds target for 5 consecutive minutes.
- Improve: top_k 5–8 for recall; raise threshold to drop noise; reranker (Q1 2026);
  VPC peering for large indexes.

---

# Part 11 — SLA, Uptime & Support

- Uptime: Enterprise 99.9%, Pro 99.5%. Sandbox/Starter have no SLA.
- Credits: Enterprise 10%/failed hour (cap 50%); Pro 5% (cap 25%).
- Support: Starter community (24h), Pro priority email (4 business hours),
  Enterprise dedicated engineer (1 business hour).
- Severity response: P1 1h (Enterprise), P2 4h, P3 1 business day, P4 best effort.
- Maintenance announced 72h ahead; status dashboard live; monthly SLA report day 5.

---

# Part 12 — Onboarding & Troubleshooting

- Onboard: create project, upload (PDF/TXT/MD/JSON/CSV, <50MB), verify indexing, first query, tune.
- Doc processing: file >50MB split; unsupported format rejected; malformed PDF re-export.
- No sources: doc not indexed; threshold too high; question too different (raise top_k).
- High latency: large index on low tier; top_k very high; 3072 dims (consider compact).
- Rate limits: respect Retry-After, batch under 100/min, raise cap.
- SSO: confirm IdP signs SAML/OIDC for the email domain, SSO on Pro+, refresh via OAuth.
  Legacy HS256 tokens rejected since v2.8.

---

# Part 13 — Privacy

- Collects: account (name, work email, billing), usage (auth, API logs, telemetry,
  query logs 90 days), and document content (as data processor, for your index only).
- Does not sell personal information; no ads on customer content.
- GDPR bases: contract, legitimate interests, consent (revocable). Rights supported,
  30-day response window. Account data retained life of account + 30 days.
- Sharing: sub-processors in trust portal, payment processors, legal/regulatory.
- Contact: privacy@ragpilot.io; inquiries acknowledged in 5 business days.

---

# Part 14 — Chunking & Retrieval

- Chunking: default 1000 chars, 150 overlap, paragraph-aware boundary snapping.
- Retrieval: embed question → vector search (top_k, threshold) → inject matches as
  context → LLM → answer + sources + groundedness.
- top_k: number of chunks injected (default 5). 5–8 recommended; >10 dilutes quality.
  Higher top_k = more tokens.
- Threshold: higher excludes noise but risks misses; lower includes more but adds noise.
- Cost: driven by tokens sent to the LLM; lower top_k + higher threshold = fewer tokens.
- Groundedness: High/Medium/Low, how well the answer is supported by context.

---

# Part 15 — Batch Import & SDK

Python (`pip install ragpilot`, Py 3.10+):

```python
from ragpilot import RagPilot
client = RagPilot(api_key="...")
project = client.projects.create(name="docs", region="us-east-1")
batch = client.documents.import_folder(project_id=project.id, path="./corpus")
batch.wait(timeout=1800)
```

Node (`npm install @ragpilot/sdk`, Node 18+):

```js
import { RagPilot } from "@ragpilot/sdk";
const client = new RagPilot({ apiKey: process.env.RAGPILOT_API_KEY });
const batch = client.documents.importFolder({ projectId: "p", path: "./corpus" });
await batch.wait();
```

- Concurrent uploads (default 8), retries on 429/503 with backoff, unsupported
  files reported without aborting.
- Rule: keep top_k at 5 and prefer the compact model to control token cost. RAG
  sends only relevant chunks; the "stuff everything" anti-pattern scales linearly.

---

# Part 16 — Enterprise Deployment

- Capabilities: dedicated infra, VPC peering, 99.9% SLA, dedicated support.
- Residency: `us-east-1`, `us-west-2`, or `eu-central-1`.
- **BYOK (bring-your-own-key):** Enterprise customers supply their own KMS key to
  encrypt customer documents at rest; RagPilot never has access to key material
  outside the operation, and keys can be revoked independently.
- VPC peering connects your network directly to RagPilot's internal network,
  bypassing the public internet; provisioned in 5 business days.
- **Single-tenant deployment GA in Q4 2026** (dedicated, no shared tenancy).
- Enterprise onboarding engineer; production readiness in ~15 business days.

---

# Part 17 — FAQ

- What is RagPilot? B2B SaaS for building RAG apps. HQ Austin, TX. Founders
  Andrea Villanueva (CEO) / Marcus Chen (CTO). Series A Oct 2024, $240M.
- Formats: PDF, TXT, MD, JSON, CSV (<50MB). Chunk: 1000 chars, 150 overlap.
  Default top_k 5. Embedding models: 1536 (default), 768, or 3072 per project.
- Prices: Starter $49, Pro $249, Enterprise custom; 20% annual discount. Free
  Sandbox with 100K ops + 14-day Pro trial.
- Refund: annual full in 30 days, then prorated quarterly; monthly non-refundable.
  Overage: $2 per additional 100K vector ops.
- SOC 2 Type II yes. No training on customer data. AES-256 at rest, TLS 1.2+.
  Audit logs 90 days. p95 target <1.2s up to 10M vectors.
- Base URL `https://api.ragpilot.io/v1`. Indexing 100/min, queries 300/min.
  Support: Starter community, Pro email, Enterprise dedicated.

---

# Part 18 — Benchmarks: RAG vs Full-Document

For a single ~24KB document (roughly 5.5-6K tokens) at top_k 5:

| Method | Tokens per query |
|--------|------------------|
| RAG (top_k 5) | ~1.3K–1.8K |
| Full-document baseline | ~5.5K–6K |

Over repeated queries the savings compound: RAG sends only the relevant chunk
each time, while the full-doc baseline re-reads the entire document. This corpus
is one large file on purpose: every example question's answer lives in one small
section, so RAG retrieves a single chunk while the baseline must process all of it.

---

# Part 19 — Glossary

- **RAG:** retrieve relevant chunks and inject them as context into an LLM before
  generating, grounding the answer in source material.
- **Chunk:** discrete unit of text (default 1000 chars) split and embedded.
- **Embedding:** vector representing semantic meaning; similar meanings → nearby vectors.
- **Vector index:** fast similarity search over embeddings (HNSW in pgvector).
- **top_k:** number of chunks retrieved/injected (default 5).
- **Similarity threshold:** minimum cosine similarity a candidate must exceed.
- **Groundedness:** High/Medium/Low label for how well an answer is supported.
- **Overage:** usage beyond plan allowance, billed at $2 per extra 100K ops.
- **BYOK:** Enterprise option to supply your own KMS key for at-rest encryption.
- **VPC peering:** direct cloud-to-cloud network path bypassing the public internet.
- **p95 latency:** latency below which 95% of requests fall (target <1.2s).
- **NRR:** net revenue retention (118% in 2025).

---

# Part 20 — Industry Use Cases

- **Support:** ground AI assistants in docs; retrieve the exact policy clause
  (e.g. 30-day refund + quarterly proration) instead of hallucinating.
- **Legal/Compliance:** index contracts and policy; surface the relevant clause
  and location; retention locking + exportable audit logs.
- **Engineering:** index design docs/runbooks; answer "what index rate limit?"
  (100/min) without reading the whole reference.
- **Sales:** ground pricing/deals/competitor notes; e.g. "annual Pro price"
  (pulls table + 20% discount).
- **HR:** index handbooks; new hires ask operational questions, grounded in policy.

---

# Part 21 — Tuning a Large Corpus (Worked Example)

1. **Baseline:** index a sample; record precision, groundedness, latency, tokens.
2. **Diagnose misses:** was the answer present? Did the threshold exclude it?
   Is the question phrased very differently?
3. **Adjust top_k:** raise to 6–8 if recall is missed; watch token cost.
4. **Tune threshold:** raise to drop noise; lower if answers are missed.
5. **Compare cost:** on a 6K-token single doc, RAG sends ~1.3K; stuffing sends
   ~6K. Over 100 queries: ~130K vs ~600K tokens (~4.5x).
6. **Load test:** batch queries, monitor p95 (<1.2s up to 10M vectors), scale
   horizontally if it degrades.

---

# Part 22 — Error Reference

| Code | HTTP | Meaning | Common cause |
|------|------|---------|--------------|
| unauthorized | 401 | Missing/invalid token | Expired token; wrong scope |
| invalid_request | 400 | Malformed request | Unknown field/type |
| not_found | 404 | Resource missing | Wrong id; deleted doc |
| rate_limit_exceeded | 429 | Too many requests | Over per-endpoint limit |
| quota_exceeded | 402 | Allowance spent | Out of plan allowance |
| service_unavailable | 503 | Transient provider failure | Provider overload |
| processing_failed | 422 | Extraction failed | Unsupported/corrupt file |
| storage_error | 500 | Storage failure | Object store misconfig |

---

# Part 23 — Performance Benchmarks

| Index size | top_k | Dims | p50 | p95 |
|------------|-------|------|-----|-----|
| 100K | 5 | 1536 | 380 ms | 820 ms |
| 1M | 5 | 1536 | 520 ms | 1.05 s |
| 10M | 5 | 1536 | 680 ms | 1.19 s |
| 10M | 5 | 768 | 540 ms | 0.98 s |
| 10M | 8 | 1536 | 780 ms | 1.47 s |
| 50M | 5 | 1536 | 940 ms | 1.85 s |

Token cost per query for a ~6K single doc: RAG ~1.3K vs full-doc ~6K (~4.5x).
Over 100 queries: ~130K vs ~600K.

---

# Part 24 — Migration & Upgrade Guide

- Platform upgrades are managed by RagPilot; `v1` stays backward compatible.
- Tier moves: upgrade immediate + prorated; downgrade at renewal (oversized index
  read-only); Enterprise move needs a migration engineer.
- Changing embedding model: fixed per project, so create new project + re-index
  (batch import SDK streamlines).
- Import: vector-format exports only if dims match a supported model; otherwise
  re-embed. Validate post-migration: groundedness/precision >= source, p95 in
  target, no stuck documents.

---

# Part 25 — Cost Optimization Playbook

- **Tokens:** top_k 5 unless recall demands; raise threshold; prefer compact 768.
  Use RAG, not stuffing (send only relevant chunks).
- **Overage:** monitor usage; index once, query many; raise cap before spikes.
- **Latency:** pin region near workload; VPC peering; add hybrid/rerank only when
  precision requires (adds a step).
- **Index:** compact 768 model; purge obsolete docs; retention locking (Enterprise).

---

# Part 26 — Data Dictionary

| Object | Fields | Notes |
|--------|--------|-------|
| Workspace | id, name, region, plan | Top-level tenant partition |
| Project | id, name, region, embedding_model, vector_count | Owns an index |
| Document | id, project_id, filename, storage_path, status, chunks | Source file |
| Chunk | id, document_id, chunk_index, content, embedding | Retrieved unit |
| Query | id, question, answer, model, latency, groundedness, tokens | Logged per query |
| Comparison | id, query, rag_answer, baseline_answer, metrics | RAG vs full-doc |
| API token | id, scopes, expires_at | Server or user token |

---

# Part 27 — Validation Checklist

Retrieval: every critical question High/Medium-grounded; no empty sources when the
answer exists; top_k/threshold tuned. Performance: p95 <1.2s; token cost far below
full-doc. Security/Compliance: SSO on Pro+, exportable audit logs, residency pinned
at creation, BYOK where required. Operations: billing cap set, status/webhook
subscribed, re-index runbook exists.

---

# Part 28 — FAQ (Supplement)

- Can I mix embedding models in one project? No — fixed per project; new project
  to change.
- Data on downgrade? Takes effect at renewal; oversized index read-only.
- Free trial? 14-day Pro trial on Sandbox from first upload.
- Regions? us-east-1, us-west-2, eu-central-1; chosen at creation, not changeable.
- Export? Chunks + embeddings via API (JSON); raw downloads until purged; exports
  not billed.

---

# Part 29 — Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| rag_top_k | 5 | Chunks retrieved per query |
| rag_min_score | 0.25 | Min cosine similarity to be injected |
| grounded_high | 0.72 | At/above this similarity = groundedness High |
| grounded_medium | 0.48 | At/above this similarity = groundedness Medium |
| embedding_dim | 1536 | Output dims of the embedding model |
| chunk_size | 1000 | Chars per chunk |
| chunk_overlap | 150 | Overlap between adjacent chunks |

---

# Part 30 — Reference Answers for Common Queries

- **Who founded RagPilot and who is CEO?** Andrea Villanueva (CEO), Marcus Chen (CTO).
  Founded 2023, Austin TX. Series A Oct 2024 at $240M.
- **2025 revenue?** $12.4M (up 58% from $7.8M). ARR $6.2M→$11.9M. NRR 118%.
- **Monthly prices?** Sandbox $0, Starter $49, Pro $249, Enterprise custom; 20% annual discount.
- **Refund policy?** Annual: full in 30 days, then prorated quarterly. Monthly
  non-refundable beyond current period. 5 business days to process.
- **Over allowance?** Starter/Pro stop indexing until cap raised/reset. Overage $2
  per extra 100K ops, billed month end. Enterprise no auto-overage.
- **Rate limits?** Indexing 100/min, queries 300/min, project 60/min, metadata 500/min.
- **Scopes to create a document?** `write:documents` (POST + DELETE). Client-creds
  only GET /projects + POST /queries with granted scopes.
- **BYOK?** Yes on Enterprise: own KMS key for at-rest encryption, revocable.
- **Audit logs?** 90 days, exportable.
- **SOC 2?** Yes Type II (security, availability, confidentiality). ISO 27001 in progress.
- **Train on customer data?** No.
- **p95 latency target?** <1.2s for up to 10M vectors at top_k 5.
- **Model that reduces storage cost?** `ragpilot-embed-compact` (768 dims).
- **Single-tenant GA?** Q4 2026.
- **File formats?** PDF, TXT, MD, JSON, CSV (<50MB).
- **Use different models in one project?** No; fixed per project, create new to change.

*End of RagPilot complete knowledge base. Single fictitious document intended to
demonstrate retrieval-augmented generation across a large corpus.*
