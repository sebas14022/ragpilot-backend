-- Storage policies for the ragpilot-docs bucket.
-- NOTE: the bucket itself must be created via the dashboard or SDK (see
-- scripts/create_bucket.py). These policies apply once the bucket exists.

insert into storage.buckets (id, name, public)
values ('ragpilot-docs', 'ragpilot-docs', false)
on conflict (id) do nothing;

-- Owner can create/read/delete objects under /{owner-user-id}/...
drop policy if exists ragpilot_owner_insert on storage.objects;
create policy ragpilot_owner_insert on storage.objects
  for insert with check (
    bucket_id = 'ragpilot-docs' and auth.uid()::text = (storage.foldername(name))[1]
  );

drop policy if exists ragpilot_owner_select on storage.objects;
create policy ragpilot_owner_select on storage.objects
  for select using (
    bucket_id = 'ragpilot-docs' and auth.uid()::text = (storage.foldername(name))[1]
  );

drop policy if exists ragpilot_owner_delete on storage.objects;
create policy ragpilot_owner_delete on storage.objects
  for delete using (
    bucket_id = 'ragpilot-docs' and auth.uid()::text = (storage.foldername(name))[1]
  );
