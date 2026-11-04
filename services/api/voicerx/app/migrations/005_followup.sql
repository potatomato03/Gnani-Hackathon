-- Follow-up state shares the doctor's private app schema and approved version.
create table if not exists app.followups (
  id text primary key,
  encounter_id text not null references app.encounters,
  version int not null,
  organisation_id text not null references app.organisations,
  patient_id text not null references app.patients,
  conversation jsonb not null,
  join_hash text unique,
  join_expires_at timestamptz,
  updated_at timestamptz not null default now(),
  unique (encounter_id, version),
  foreign key (encounter_id, version, status) references app.report_versions(encounter_id, version, status),
  status text not null default 'approved' check (status = 'approved')
);
create table if not exists app.whatsapp_events (
  id text primary key,
  payload jsonb not null,
  state text not null default 'pending' check (state in ('pending','running','done','failed')),
  attempts int not null default 0,
  not_before timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  error text
);
create table if not exists app.whatsapp_receipts (
  message_id text primary key,
  followup_id text not null references app.followups,
  message_ref text not null,
  status text not null default 'accepted',
  updated_at timestamptz not null default now()
);
create index if not exists followups_scope_idx on app.followups(organisation_id, patient_id);
create index if not exists whatsapp_events_claim_idx on app.whatsapp_events(state, not_before);
