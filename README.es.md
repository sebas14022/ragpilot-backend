# RagPilot Backend

> **English:** [README.md](README.md)

Construí este backend para RagPilot para demostrar, con números reales, por qué
la Retrieval-Augmented Generation le gana a la alternativa ingenua para las
operaciones diarias y los chatbots. Ingiere documentos del usuario en
**Supabase pgvector** con embeddings de Gemini, y genera respuestas a través de
**Groq** (con fallback a **Gemini**).

El endpoint `/compare` es el corazón de todo: sobre la misma pregunta corre RAG
(recuperar solo los chunks relevantes) contra un baseline "full-doc" que mete
todo el corpus en un solo prompt. Concluí que la forma honesta de compararlos
es mantener el mismo modelo en ambas ramas, para que la única variable sea si
el contexto fue recuperado o metido entero. El contraste de tokens, latencia y
groundedness es visible en la UI y se agrega en el dashboard.

Para el proyecto completo — por qué RAG importa, la arquitectura y las
decisiones que tomé — leé [PROJECT_OVERVIEW.es.md](PROJECT_OVERVIEW.es.md).

## Stack

| Capa | Tecnología |
|---|---|
| API | FastAPI (async) + Uvicorn |
| Vector store | Supabase Postgres + `pgvector` (coseno, HNSW) |
| Storage | Supabase Storage (bucket privado por usuario) |
| Auth | Supabase Auth (JWT ES256, validado del lado del servidor) |
| Embeddings | `gemini-embedding-001` (1536 dims, normalizados) |
| LLM | Groq `openai/gpt-oss-120b` (primario), Gemini (fallback) |
| Contrato frontend | camelCase vía alias de Pydantic |

## Arquitectura

```
app/
  main.py            app FastAPI, CORS, montaje de routers (/v1)
  config.py          settings Pydantic desde env / .env
  auth.py            dependencia JWT -> 401 o UserContext
  db.py              cliente compartido de Supabase con service-role
  schemas.py         modelos Pydantic de request/response (alias camelCase)
  routers/
    health.py        GET /v1/health
    documents.py     subir / listar / borrar documentos
    rag.py           POST /v1/rag/query
    compare.py       POST /v1/compare (RAG vs baseline full-doc)
    metrics.py       KPIs del dashboard, serie de queries, queries recientes
  rag_service.py     pipeline compartido: retrieve -> prompt -> generate (+ run_stuffed)
  embeddings.py      cliente de embeddings de Gemini (normalización)
  chunking.py        chunking de tamaño fijo con overlap + ajuste a límites
  text_extraction.py PDF / TXT / MD / JSON / CSV -> texto plano
  groundedness.py    etiqueta híbrida heurística + LLM opcional
scripts/
  create_bucket.py   crea el bucket privado de Storage
  seed.py            siembra métricas de query de ejemplo para un usuario
  seed_corpus.py     indexa el documento grande de demo para un usuario
migrations/
  000_full.sql       setup completo de una sola pasada (schema + RLS + search + storage)
  001_init.sql       schema, RLS, match_documents
  002_storage.sql    bucket de storage + políticas por dueño
  003_comparison_metrics.sql  columnas de latencia en comparisons
  004_chunk_ownership_rls.sql  RLS de defensa en profundidad en document_chunks
  005_drop_legacy_precision.sql  elimina las columnas "precision" retiradas
tests/               suite pytest (auth, documents, chunking, compare, rag_service,
                     groundedness, prompt, metrics)
```

El backend se autentica ante Supabase con la key **service_role** para poder
bypassear RLS y gestionar vectores/storage en nombre de cualquier usuario. El
browser nunca recibe esa key — solo posee el access token de Supabase Auth del
usuario.

## Setup

1. Clonar el repo y crear un entorno virtual.

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```

2. Crear `.env` desde el ejemplo y completar los valores reales.

   ```powershell
   Copy-Item .env.example .env
   ```

   Variables requeridas (ver `app/config.py` para los defaults):

   | Variable | Propósito |
   |---|---|
   | `SUPABASE_URL` | URL del proyecto Supabase |
   | `SUPABASE_SERVICE_ROLE_KEY` | key del lado del servidor (nunca expuesta) |
   | `SUPABASE_JWT_SECRET` | secreto HS256 usado para validar los JWTs de usuario |
   | `GEMINI_API_KEY` | API key de Google AI Studio (embeddings + fallback LLM) |
   | `GEMINI_MODEL` | modelo LLM de fallback |
   | `GEMINI_EMBEDDING_MODEL` | modelo de embeddings, default `gemini-embedding-001` |
   | `EMBEDDING_DIM` | dimensionalidad del vector, default `1536` (debe matchear el schema) |
   | `GROQ_API_KEY` | API key de Groq (LLM primario) |
   | `GROQ_MODEL` | modelo LLM primario, default `openai/gpt-oss-120b` |
   | `MAX_DOCUMENT_CHARS` | presupuesto por documento / por corpus, default `24000` (~6K tokens) |

3. Aplicar el schema de la base de datos.

   Pegar `migrations/000_full.sql` en el SQL Editor de Supabase y ejecutar (o
   `supabase db push`). Esto crea las tablas, las políticas RLS, la función `match_documents` y el
   bucket de storage. No se necesitan otros archivos de migración para un setup
   nuevo.

4. Crear el bucket de Storage (idempotente).

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.create_bucket
   ```

5. Levantar el servidor.

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

   Docs interactivos en http://localhost:8000/docs.

## Endpoints (todos bajo `/v1`)

Los endpoints autenticados requieren `Authorization: Bearer <access_token>`
donde el token lo emite Supabase Auth para el usuario logueado.

| Método | Path | Descripción | Auth |
|---|---|---|---|
| GET | `/v1/health` | probe de liveness | No |
| POST | `/v1/documents` | subir un documento (multipart) | Sí |
| GET | `/v1/documents` | listar los documentos del usuario | Sí |
| POST | `/v1/documents/{doc_id}/delete` | borrar un documento + sus chunks | Sí |
| POST | `/v1/rag/query` | preguntar sobre el contexto | Sí |
| POST | `/v1/compare` | respuesta RAG vs baseline sin contexto | Sí |
| GET | `/v1/metrics/dashboard` | KPIs (documentos, chunks, queries, tokens) | Sí |
| GET | `/v1/metrics/query-series` | serie mensual de queries/chunks | Sí |
| GET | `/v1/metrics/recent-queries` | últimas 20 queries | Sí |

### `/v1/rag/query`

```json
{
  "question": "What does the onboarding policy say about remote work?",
  "documentIds": []   // opcional; restringe la recuperación a estos documentos
}
```

Cuando `documentIds` se provee y no está vacío, la recuperación se limita a esos
documentos. Si se omite, se buscan todos los documentos indexados del usuario.

Respuesta (`ChatResponse`):

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

Corre la pipeline RAG contra un **baseline full-doc**. RAG recupera solo los
chunks relevantes y los inyecta como contexto; el baseline usa `run_stuffed`
para meter todo el corpus de documentos seleccionado en un solo prompt (el
anti-patrón que RAG reemplaza). Cada request hace **dos** llamadas al LLM y
reporta latencia, tokens, contexto usado y groundedness para ambas ramas.

```json
{
  "query": "Which version was released more recently by date, v2.4 or v2.8?",
  "documentIds": ["<doc-uuid>"]   // opcional; restringe recuperación/corpus a estos
}
```

Cuando `documentIds` se provee y no está vacío, ambas pipelines se limitan a
esos documentos. Si se omite, se usa todo el corpus del usuario. Como el
baseline mete toda la selección en un solo prompt, el corpus seleccionado total
debe quedar bajo `MAX_DOCUMENT_CHARS` (24.000 caracteres) — el endpoint devuelve
`422` antes de ejecutar nada si la selección lo supera.

## Formatos de documento soportados

- PDF (`.pdf`) — extracción de texto vía `pypdf`
- Texto plano / Markdown (`.txt`, `.md`)
- JSON (`.json`) — pretty-printed
- CSV (`.csv`) — filas unidas con pipe

## Groundedness

Las respuestas se etiquetan `High` / `Medium` / `Low` con una estrategia
**híbrida**:

- Si la similitud de recuperación está claramente por arriba/abajo de los
  umbrales (`0.72` high / `0.48` medium por defecto), la etiqueta se deriva del
  score — sin costo extra de LLM.
- Solo en la banda ambigua `Medium` se corre una verificación corta con LLM
  (`GROUNDEDNESS_LLM_FALLBACK=true` por defecto) que juzga si la respuesta está
  realmente soportada por el contexto.

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Cobertura (tests unitarios, sin llamadas a APIs live): auth, documents
(upload/list/delete), chunking, presupuesto del compare + filtrado de
documentos, rag_service recuperación/prompts, groundedness, métricas de
comparación, métricas del dashboard.

## Sembrar métricas de ejemplo

```powershell
.\.venv\Scripts\python.exe -m scripts.seed <user_email>
```

Inserta filas de query generadas para un usuario de modo que el dashboard tenga
datos que mostrar.

## Sembrar el corpus demo

El archivo único `docs/sample_document_large.md` contiene una base de
conocimiento ficticia de RagPilot: **~20.8 KB / ~5.2K tokens / 30 chunks**. Es
un solo archivo a propósito: el contraste RAG-vs-full-doc (Parte 23 del doc)
depende de un documento grande con muchas secciones. Está escrito a propósito
para que varias preguntas tengan respuestas fáciles de errar cuando todo el
documento se mete en un solo prompt (p. ej. "Which version is more recent by
date, v2.4 or v2.8?" — la lista no es cronológica). Indexalo para un usuario
para que el contraste sea significativo:

```powershell
.\.venv\Scripts\python.exe -m scripts.seed_corpus <user_email>
```

Esto trocea, embeddea e indexa el archivo único con las funciones reales del
pipeline usando el cliente service-role. Seleccioná el documento resultante en
la UI antes de correr comparaciones.