-- Keep dashboard patient memory private alongside conversations and clinical records.
create table if not exists app.patient_memory (
  id text primary key, patient_key text not null, visit_ref text not null, kind text not null,
  text text not null, quote text, source text not null, source_ref text, at timestamptz not null,
  synthetic boolean not null default true check (synthetic)
);
create index if not exists app_patient_memory_key_idx on app.patient_memory(patient_key, at desc);
create table if not exists app.patient_documents (
  id text primary key, patient_key text not null, visit_ref text not null, mime text not null,
  sha256 text not null, pages int, method text not null, reading jsonb not null,
  received_at timestamptz not null, synthetic boolean not null default true check (synthetic),
  unique (patient_key, sha256)
);
alter table app.patient_memory enable row level security;
alter table app.patient_documents enable row level security;
