-- RagPilot — defense-in-depth RLS on public.document_chunks.
-- Tightens the insert policy so chunk.user_id must match the owning
-- document's user_id (prevents cross-tenant writes by a stray privileged key).
-- Apply in the Supabase SQL Editor (idempotent).

drop policy if exists document_chunks_insert_service on public.document_chunks;

create policy document_chunks_insert_service on public.document_chunks
  for insert with check (
    exists (
      select 1 from public.documents d
      where d.id = document_id
        and d.user_id = user_id
    )
  );