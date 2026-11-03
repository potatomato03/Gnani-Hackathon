-- The medicines usually prescribed for a visit's conditions, offered first when the doctor adds a medicine
-- (runbook D-122). Made once per visit; a suggestion list, never part of the record. Safe to rerun.
create table if not exists app.medicine_shortlists (
  encounter_id text primary key references app.encounters,
  conditions text[] not null,
  items jsonb not null,
  method jsonb not null,
  created_at timestamptz not null default now()
);
