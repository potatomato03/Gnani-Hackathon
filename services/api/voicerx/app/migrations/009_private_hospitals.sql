-- Invite-only demo workspace. Existing clinical snapshots are retained, never rewritten.
alter table app.organisations add column if not exists archived_at timestamptz;
alter table app.users add column if not exists workspace_admin boolean not null default false;
alter table app.users add column if not exists disabled_at timestamptz;
alter table app.patients add column if not exists assigned_doctor_id text references app.users;
alter table app.patients add column if not exists phone_encrypted text;
alter table app.patients add column if not exists phone_last4 text;
alter table app.patients add column if not exists registered_by text references app.users;
alter table app.sessions add column if not exists operator_id text references app.users;

create table if not exists app.login_accounts (
  username text primary key,
  user_id text not null unique references app.users,
  password_hash text not null,
  disabled_at timestamptz,
  created_at timestamptz not null default now()
);
create table if not exists app.login_limits (
  key text primary key,
  attempts int not null default 0,
  window_started timestamptz not null default now(),
  blocked_until timestamptz
);
create table if not exists app.source_files (
  source_id text primary key references app.sources,
  sha256 text not null,
  data bytea not null check(octet_length(data)<=41943040)
);
create table if not exists app.artifact_files (
  artifact_id text primary key references app.artifacts,
  sha256 text not null,
  data bytea not null
);
create table if not exists app.audio_uploads (
  id text primary key,
  encounter_id text not null references app.encounters,
  user_id text not null references app.users,
  media_type text not null,
  language text not null,
  size_bytes int not null check(size_bytes between 1 and 41943040),
  expires_at timestamptz not null default now()+interval '1 hour'
);
create table if not exists app.audio_upload_chunks (
  upload_id text not null references app.audio_uploads on delete cascade,
  part int not null check(part between 0 and 13),
  data bytea not null check(octet_length(data) between 1 and 3145728),
  primary key(upload_id,part)
);
create table if not exists app.whatsapp_contact_windows (
  contact text primary key,
  last_inbound_at timestamptz not null
);
create table if not exists app.whatsapp_active_reports (
  contact text primary key,
  followup_id text not null references app.followups,
  updated_at timestamptz not null default now()
);
alter table app.whatsapp_contact_windows add column if not exists opted_out_at timestamptz;
alter table app.audio_uploads add column if not exists source_id text references app.sources;
alter table app.clinic_report_jobs add column if not exists delivery_mode text not null default 'clinic_copy'
  check(delivery_mode in ('clinic_copy','patient'));
alter table app.login_accounts enable row level security;
alter table app.login_limits enable row level security;
alter table app.source_files enable row level security;
alter table app.artifact_files enable row level security;
alter table app.audio_uploads enable row level security;
alter table app.audio_upload_chunks enable row level security;
alter table app.whatsapp_contact_windows enable row level security;
alter table app.whatsapp_active_reports enable row level security;
