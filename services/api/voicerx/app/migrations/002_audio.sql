-- Recorded or uploaded audio as a visit's source, transcribed by the worker. Safe to rerun.
alter table app.sources alter column text drop not null;
alter table app.sources alter column text_sha256 drop not null;
alter table app.sources add column if not exists media_type text;
alter table app.sources add column if not exists file_name text;
alter table app.sources add column if not exists sha256 text;
alter table app.sources add column if not exists duration_s numeric(8, 1);
-- Who confirmed the patient agreed to this recording, and when (DESIGN.md 5.2: a checkbox alone is not the record).
alter table app.sources add column if not exists consent jsonb;
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'sources_kind_content') then
    alter table app.sources add constraint sources_kind_content check (
      (kind = 'typed' and text is not null) or (kind = 'audio' and file_name is not null and consent is not null));
  end if;
end $$;

-- The transcript belongs to the run that made it; a retry reuses it instead of paying Prisma again.
alter table app.runs add column if not exists transcript text;
alter table app.runs add column if not exists transcript_meta jsonb;
