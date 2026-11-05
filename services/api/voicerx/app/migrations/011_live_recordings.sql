-- A recording sent in pieces while the visit goes on, transcribed as it arrives (runbook D-131).
-- The pieces, joined in order, are the browser's own file; it becomes the visit's source when the doctor
-- creates the report, and the run starts with the transcript already made. Each piece is its own row,
-- so taking one never rewrites what came before.
create table if not exists app.live_recordings (
  id text primary key,
  encounter_id text not null references app.encounters,
  user_id text not null references app.users,
  media_type text not null,
  language text not null,
  next_part int not null default 0 check(next_part between 0 and 400),
  bytes int not null default 0 check(bytes between 0 and 41943040),
  texts jsonb not null default '[]'::jsonb,
  done_samples bigint not null default 0,
  total_samples bigint not null default 0,
  segments int not null default 0,
  finished boolean not null default false,
  error text,
  source_id text references app.sources,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '6 hours'
);
alter table app.live_recordings drop column if exists data;
alter table app.live_recordings add column if not exists bytes int not null default 0 check(bytes between 0 and 41943040);
create index if not exists live_recordings_encounter on app.live_recordings(encounter_id);
create table if not exists app.live_recording_parts (
  live_id text not null references app.live_recordings on delete cascade,
  part int not null check(part between 0 and 400),
  data bytea not null check(octet_length(data) between 0 and 3145728),
  primary key (live_id, part)
);
alter table app.live_recording_parts alter column data set storage external;
alter table app.live_recordings enable row level security;
alter table app.live_recording_parts enable row level security;
