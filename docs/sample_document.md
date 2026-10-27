# RagPilot — Company & Product Handbook

This document is a fictional knowledge base for RagPilot, used to demonstrate how
RAG (retrieval-augmented generation) answers questions grounded in source material.

## Company Overview

RagPilot is a B2B SaaS platform that helps teams build retrieval-augmented
generation applications on top of their own document stores. The product offers
managed indexing, embeddings, and query APIs with per-tenant isolation.

Founded in 2023, RagPilot is headquartered in Austin, Texas, with a remote-first
engineering team distributed across North America and Europe.

## Leadership & Milestones

RagPilot is co-founded by **Andrea Villanueva** (CEO) and **Marcus Chen** (CTO).
The company's Series A round closed in **October 2024** at a $240M valuation, led
by Meridian Ventures.

- **v1.0** — released May 2023.
- **v2.0** — released February 2025; introduced the managed embeddings API.
- **v2.8** — released **March 4, 2025**; added per-tenant isolation and SSO.
- The platform ended 2025 with **1,284 paying customers**.

## Revenue 2025

RagPilot's total revenue for fiscal year 2025 was $12.4M, up 58% year over year
from $7.8M in 2024. Annual recurring revenue (ARR) grew from $6.2M to $11.9M over
the same period.

The growth was driven primarily by the self-serve tier: 68% of new customers in
2025 started as self-serve trials. Net revenue retention ended the year at 118%.

## Pricing and Refund Policy

RagPilot offers three plans:

- **Starter** — $49/month. Up to 3 projects, 1M vector operations per month,
  community support.
- **Pro** — $249/month. Unlimited projects, 10M vector operations per month,
  priority email support, SSO.
- **Enterprise** — custom pricing. Dedicated infrastructure, VPC peering, 99.9%
  SLA, dedicated support engineer.

Annual plans are billed at a 20% discount compared to monthly billing.

**Refund policy for annual plans:** Customers on annual plans may request a full
refund within the first 30 days of the subscription term, no questions asked.
After 30 days, refunds are prorated on a quarterly basis. Refund requests are
processed within 5 business days and are made to the original payment method.
Monthly plans are non-refundable beyond the current billing period.

## Security and Compliance Posture

RagPilot is SOC 2 Type II certified and GDPR compliant. Data at rest is encrypted
with AES-256, and data in transit uses TLS 1.2 or higher.

All customer embeddings and documents are isolated per tenant. Access control is
enforced via short-lived signed tokens and fine-grained role-based permissions.
Audit logs are retained for 90 days and are exportable on request.

RagPilot does not train foundation models on customer data. Customer documents
are only ever used to power their own retrieval index.

## Onboarding Policy: Remote Work

RagPilot is remote-first. New hires may work from anywhere in the United States
or from approved EU locations. Remote work is the default; no office attendance
is required unless the role explicitly states otherwise.

## Data Storage and Retention (S3 Buckets)

RagPilot stores raw customer documents and derived artifacts in S3.

- Raw uploads are stored in a private bucket and marked for deletion **after 90
  days** unless the account is on a paid plan.
- Processed chunks and embeddings are stored in a separate bucket and retained
  for the life of the project, or until the project is deleted.
- Deleted projects trigger an immediate purge of all associated objects in both
  buckets. The retention window is not applied retroactively to deleted projects.

## API Access: OAuth Scopes

The following REST endpoints require OAuth scopes:

- `GET /v1/projects` — requires the `read:projects` scope.
- `POST /v1/projects` — requires the `write:projects` scope.
- `POST /v1/documents` — requires the `write:documents` scope.
- `DELETE /v1/documents/{id}` — requires the `write:documents` scope.
- `GET /v1/queries` — requires the `read:queries` scope.
- `POST /v1/queries` — requires the `query:execute` scope.

Anonymous (client credentials) tokens may only call `GET /v1/projects` and
`POST /v1/queries` with the corresponding scopes granted by an admin.

## Production Monitoring: p95 Latency

RagPilot monitors end-to-end query latency, defined as the time from when a query
is submitted until a full response is returned.

In production, p95 latency is monitored per tenant and per index size tier. The
target is to keep p95 latency under 1.2 seconds for indexes up to 10M vectors.
Latency is tracked with a Prometheus counter and surfaced on the live status
dashboard. Alerts fire when p95 latency exceeds the target for five consecutive
minutes.

## Example: RAG Pipeline Internals

When a query comes in, RagPilot embeds the question, runs a vector similarity
search against the tenant's index (configurable top-k, default 5, with a
similarity threshold), retrieves the matching chunks, injects them as context
into an LLM prompt, and returns the generated answer together with the sources
used and a groundedness score.
