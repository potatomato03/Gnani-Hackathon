-- Clinic products, stored suggestions for unclear medicine names, and each doctor's past choices
-- (spec 2026-11-03, parts B and C). Safe to rerun.

-- Products the dataset lacks, added by a doctor (or later imported from a hospital's drug master).
-- Composition uses the dataset's form, "Ingredient (40mg) + Ingredient (10mg)".
create table if not exists app.clinic_products (
  id text primary key,
  organisation_id text not null references app.organisations,
  name text not null,
  manufacturer text,
  form text not null,
  composition text not null,
  status text not null default 'pending_review' check (status in ('pending_review', 'reviewed', 'withdrawn')),
  source text not null default 'doctor' check (source in ('doctor', 'import')),
  created_by text references app.users,
  created_at timestamptz not null default now()
);

-- Ranked suggestions for one medicine of one visit, made once by the worker beside the draft.
create table if not exists app.medicine_suggestions (
  encounter_id text not null references app.encounters,
  medication_id text not null,
  heard text not null,
  suggestions jsonb not null,
  method jsonb not null,
  created_at timestamptz not null default now(),
  primary key (encounter_id, medication_id)
);

-- What a doctor confirmed a heard name to mean (a sound-alike -> Pan 40). It ranks first next time; it never
-- applies on its own.
create table if not exists app.medicine_aliases (
  organisation_id text not null references app.organisations,
  doctor_id text not null references app.users,
  heard_key text not null,
  product_id text not null,
  times int not null default 1,
  last_at timestamptz not null default now(),
  primary key (organisation_id, doctor_id, heard_key, product_id)
);
