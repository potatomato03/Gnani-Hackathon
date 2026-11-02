-- Application state for the doctor workspace (DESIGN.md sections 4 and 11). Safe to rerun.
-- A private schema: Supabase's Data API exposes only `public`, so only the backend reaches these tables.
create schema if not exists app;
revoke all on schema app from public;
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'anon') then execute 'revoke all on schema app from anon, authenticated'; end if;
end $$;

create table if not exists app.organisations (
  id text primary key,
  name text not null,
  timezone text not null default 'Asia/Kolkata',
  synthetic boolean not null default false
);

create table if not exists app.users (
  id text primary key,
  display_name text not null,
  registration_no text,
  specialty text,
  synthetic boolean not null default false
);

create table if not exists app.memberships (
  user_id text not null references app.users,
  organisation_id text not null references app.organisations,
  role text not null check (role in ('doctor', 'reception', 'admin')),
  primary key (user_id, organisation_id)
);

create table if not exists app.patients (
  id text primary key,
  organisation_id text not null references app.organisations,
  mrn text not null,
  name text not null,
  sex text,
  birth_year int,
  phone text,
  language_pref text not null,
  allergy_status text not null check (allergy_status in ('nka', 'known', 'unknown')),
  allergies text[] not null default '{}',
  consents text[] not null default '{}',
  synthetic boolean not null default false,
  created_at timestamptz not null default now(),
  unique (organisation_id, mrn),
  unique (organisation_id, id)
);

create table if not exists app.encounters (
  id text primary key,
  organisation_id text not null,
  patient_id text not null,
  clinician_id text not null references app.users,
  visit_date date not null,
  state text not null default 'open' check (state in ('open', 'processing', 'in_review', 'approved', 'failed')),
  current_version int,
  approved_version int,
  created_at timestamptz not null default now(),
  -- An encounter can only point at a patient of its own organisation.
  foreign key (organisation_id, patient_id) references app.patients (organisation_id, id)
);
create index if not exists encounters_patient_idx on app.encounters (patient_id, created_at desc);

create table if not exists app.sources (
  id text primary key,
  encounter_id text not null references app.encounters,
  version int not null default 1,
  kind text not null check (kind in ('typed', 'audio')),
  language text not null,
  text text not null,
  text_sha256 text not null,
  created_by text not null references app.users,
  created_at timestamptz not null default now()
);

create table if not exists app.runs (
  id text primary key,
  encounter_id text not null references app.encounters,
  source_id text not null references app.sources,
  source_version int not null,
  state text not null default 'queued'
    check (state in ('queued', 'running', 'retry_wait', 'succeeded', 'failed', 'incomplete', 'cancelled')),
  stage text,
  steps jsonb not null,
  attempts int not null default 0,
  max_attempts int not null default 3,
  lease_until timestamptz,
  not_before timestamptz not null default now(),
  error text,
  draft_version int,
  config jsonb not null default '{}',
  created_by text not null references app.users,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists runs_claim_idx on app.runs (state, not_before);

-- Every draft version and the approved snapshot, as the engine's canonical JSON.
create table if not exists app.report_versions (
  encounter_id text not null references app.encounters,
  version int not null,
  status text not null check (status in ('draft', 'approved')),
  report jsonb not null,
  content_hash text not null,
  run_id text references app.runs,
  created_by text references app.users,
  created_at timestamptz not null default now(),
  primary key (encounter_id, version, status)
);

create table if not exists app.approvals (
  id text primary key,
  encounter_id text not null references app.encounters,
  version int not null,
  content_hash text not null,
  approver_id text not null references app.users,
  approved_at timestamptz not null,
  unique (encounter_id, version)
);

-- The outbox: approval inserts pending artifacts in its own transaction; the worker renders them.
create table if not exists app.artifacts (
  id text primary key,
  encounter_id text not null references app.encounters,
  approval_id text not null references app.approvals,
  version int not null,
  kind text not null,
  state text not null default 'pending' check (state in ('pending', 'running', 'ready', 'failed', 'superseded')),
  file_name text,
  sha256 text,
  attempts int not null default 0,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists app.sessions (
  token_hash text primary key,
  user_id text not null references app.users,
  organisation_id text not null references app.organisations,
  csrf_token text not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);

create table if not exists app.audit_events (
  id bigserial primary key,
  at timestamptz not null default now(),
  actor_id text,
  organisation_id text,
  action text not null,
  entity text not null,
  entity_id text,
  detail jsonb not null default '{}'
);
