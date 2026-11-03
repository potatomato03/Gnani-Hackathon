-- Per-patient memory for the follow-up bot (runbook D-118). Synthetic data only; no phone numbers, files or audio.
-- Row-level security on with no policy: only the backend reads, over the database connection (as D-103).
create table if not exists patient_memory (
  id text primary key, patient_key text not null, visit_ref text not null, kind text not null,
  text text not null, quote text, source text not null, source_ref text, at timestamptz not null,
  synthetic boolean not null default true check (synthetic));
create index if not exists patient_memory_by_patient on patient_memory (patient_key, at desc);
create table if not exists patient_documents (
  id text primary key, patient_key text not null, visit_ref text not null, mime text not null,
  sha256 text not null, pages int, method text not null, reading jsonb not null,
  received_at timestamptz not null, synthetic boolean not null default true check (synthetic),
  unique (patient_key, sha256));
alter table patient_memory enable row level security;
alter table patient_documents enable row level security;
