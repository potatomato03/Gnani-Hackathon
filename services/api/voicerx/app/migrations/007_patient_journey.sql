-- Persistent, verified patient channel; actual numbers remain in the backend test allowlist.
create table if not exists app.patient_channels (
  patient_id text primary key references app.patients,
  organisation_id text not null references app.organisations,
  contact text not null unique,
  verified_at timestamptz not null default now(),
  last_inbound_at timestamptz,
  opted_out_at timestamptz,
  foreign key (organisation_id, patient_id) references app.patients(organisation_id, id)
);
-- Preserve verified JOIN links from the earlier integration; never infer a link from a chart phone field.
insert into app.patient_channels(patient_id, organisation_id, contact, last_inbound_at)
select patient_id, organisation_id, contact, last_inbound_at from (
  select distinct on (conversation->>'contact') patient_id, organisation_id,
         conversation->>'contact' as contact, (conversation->>'last_inbound_at')::timestamptz as last_inbound_at
  from app.followups where conversation->>'contact' is not null
    and conversation->>'stopped' = 'false' and conversation->>'last_inbound_at' is not null
  order by conversation->>'contact', updated_at desc
) verified on conflict do nothing;

-- Durable patient deliveries. Approval queues a PDF; only an explicit request queues speech.
create table if not exists app.patient_deliveries (
  id text primary key,
  followup_id text not null references app.followups,
  kind text not null check(kind in ('report_pdf','prescription_voice')),
  request_ref text not null,
  language text,
  state text not null default 'pending' check(state in
    ('pending','waiting_for_contact','waiting_for_window','waiting_for_artifact','accepted','delivered','read','failed','cancelled')),
  attempts int not null default 0,
  not_before timestamptz not null default now(),
  provider_id text,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(followup_id,kind,request_ref)
);
create index if not exists patient_deliveries_work_idx on app.patient_deliveries(state,not_before);

-- Original digital files and approved PDFs stay private and survive a local artifact-disk loss.
create table if not exists app.report_files (
  encounter_id text not null,
  version int not null,
  sha256 text not null,
  data bytea not null,
  status text not null default 'approved' check(status='approved'),
  primary key(encounter_id,version),
  foreign key(encounter_id,version,status) references app.report_versions(encounter_id,version,status)
);
create table if not exists app.patient_uploads (
  id text primary key,
  organisation_id text not null,
  patient_id text not null,
  encounter_id text not null references app.encounters,
  mime text not null,
  sha256 text not null,
  data bytea not null check(octet_length(data) <= 10000000),
  summary text not null,
  reading jsonb,
  summary_state text not null check(summary_state in ('ready','needs_review')),
  reviewed_by text references app.users,
  reviewed_at timestamptz,
  received_at timestamptz not null default now(),
  unique(organisation_id,patient_id,sha256),
  foreign key(organisation_id,patient_id) references app.patients(organisation_id,id)
);
alter table app.patient_channels enable row level security;
alter table app.patient_deliveries enable row level security;
alter table app.report_files enable row level security;
alter table app.patient_uploads enable row level security;
create table if not exists app.patient_contact_requests (
  patient_id text primary key references app.patients,
  organisation_id text not null references app.organisations,
  expected_contact text not null,
  updated_at timestamptz not null default now(),
  foreign key(organisation_id,patient_id) references app.patients(organisation_id,id)
);
alter table app.patient_contact_requests enable row level security;
