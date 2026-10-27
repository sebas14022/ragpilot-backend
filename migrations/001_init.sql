-- RagPilot schema: documents, chunks, queries, comparisons + pgvector search.

-- Enable the vector extension (requires Supabase project with pgvector available).
create extension if not exists vector;
create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- documents
-- ---------------------------------------------------------------------------
create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  filename text not null,
  storage_path text,
  status text not null default 'processing'
    check (status in ('processing', 'indexed', 'failed')),
  chunks int not null default 0,
  created_at timestamptz not null default now()
);

alter table public.documents enable row level security;

create policy documents_insert_own on public.documents
  for insert with check (auth.uid() = user_id);
create policy documents_select_own on public.documents
  for select using (auth.uid() = user_id);
create policy documents_delete_own on public.documents
  for delete using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- document_chunks  (vectors: front anon must NOT be able to read these)
-- ---------------------------------------------------------------------------
create table if not exists public.document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  chunk_index int not null,
  content text not null,
  embedding vector(1536) not null
);

alter table public.document_chunks enable row level security;

-- No SELECT policy for anon/authenticated on chunks: only the service-role
-- backend (which bypasses RLS) reads/writes vectors. Defense in depth: the
-- insert policy rejects chunks whose user_id does not match the owning
-- document's user_id, so a stray privileged key cannot write into another
-- tenant's corpus.
create policy document_chunks_insert_service on public.document_chunks
  for insert with check (
    exists (
      select 1 from public.documents d
      where d.id = document_id
        and d.user_id = user_id
    )
  );

-- ---------------------------------------------------------------------------
-- queries  (chat metrics)
-- ---------------------------------------------------------------------------
create table if not exists public.queries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  question text not null,
  answer text,
  model text,
  latency_ms int,
  groundedness text check (groundedness in ('High', 'Medium', 'Low')),
  tokens_used int,
  chunks_retrieved int not null default 0,
  status text not null default 'success'
    check (status in ('success', 'failed')),
  created_at timestamptz not null default now()
);

alter table public.queries enable row level security;

create policy queries_insert_own on public.queries
  for insert with check (auth.uid() = user_id);
create policy queries_select_own on public.queries
  for select using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- comparisons  (RAG vs baseline)
-- ---------------------------------------------------------------------------
create table if not exists public.comparisons (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  query text not null,
  rag_answer text,
  rag_model text,
  rag_latency_ms int,
  rag_groundedness text,
  rag_tokens_used int,
  baseline_answer text,
  baseline_model text,
  baseline_latency_ms int,
  baseline_groundedness text,
  baseline_tokens_used int,
  created_at timestamptz not null default now()
);

alter table public.comparisons enable row level security;

create policy comparisons_insert_own on public.comparisons
  for insert with check (auth.uid() = user_id);
create policy comparisons_select_own on public.comparisons
  for select using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- HNSW index for fast approximate nearest-neighbour search (cosine).
-- ---------------------------------------------------------------------------
create index if not exists document_chunks_embedding_hnsw
  on public.document_chunks
  using hnsw (embedding vector_cosine_ops);

create index if not exists document_chunks_document_idx
  on public.document_chunks (document_id);

-- ---------------------------------------------------------------------------
-- Vector similarity search function (scoped to a single user).
-- ---------------------------------------------------------------------------
create or replace function public.match_documents (
  query_embedding vector(1536),
  match_count int,
  match_threshold float,
  p_user_id uuid
)
returns table (
  document_id uuid,
  chunk_index int,
  content text,
  similarity float
)
language sql stable
as $$
  select
    c.document_id,
    c.chunk_index,
    c.content,
    1 - (c.embedding <=> query_embedding) as similarity
  from public.document_chunks c
  where c.user_id = p_user_id
    and (1 - (c.embedding <=> query_embedding)) >= match_threshold
  order by c.embedding <=> query_embedding
  limit match_count;
$$;

revoke execute on function public.match_documents(vector(1536), int, float, uuid) from anon;
revoke execute on function public.match_documents(vector(1536), int, float, uuid) from authenticated;
grant execute on function public.match_documents(vector(1536), int, float, uuid) to service_role;
