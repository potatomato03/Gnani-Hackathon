-- Explicit private-test clinic copies are separate from verified patient conversations.
create table if not exists app.clinic_report_contacts (
  organisation_id text not null references app.organisations,
  contact text not null,
  last_inbound_at timestamptz,
  opted_out_at timestamptz,
  primary key(organisation_id,contact)
);
create table if not exists app.clinic_report_jobs (
  id text primary key,
  organisation_id text not null references app.organisations,
  approval_id text not null references app.approvals,
  encounter_id text not null references app.encounters,
  version int not null,
  status text not null default 'approved' check(status='approved'),
  source_hash text not null,
  recipient text not null,
  kind text not null check(kind in ('report_pdf','voice_option','prescription_voice')),
  source_job text references app.clinic_report_jobs,
  request_ref text not null,
  language text not null,
  state text not null default 'pending' check(state in
    ('pending','waiting_for_window','waiting_for_artifact','accepted','sent','delivered','read','failed','cancelled')),
  provider_id text unique,
  attempts int not null default 0,
  error text,
  not_before timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key(encounter_id,version,status) references app.report_versions(encounter_id,version,status),
  unique(approval_id,recipient,kind,request_ref)
);
create index if not exists clinic_report_jobs_work on app.clinic_report_jobs(state,not_before);
alter table app.clinic_report_contacts enable row level security;
alter table app.clinic_report_jobs enable row level security;
