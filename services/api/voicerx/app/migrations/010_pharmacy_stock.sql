-- The hospital pharmacy's stock (runbook D-126 to D-128). Each import is a full snapshot that replaces the
-- previous one; rows keep the pharmacy's own item code and name beside the catalogue product they were matched
-- to. Stock only ranks and labels; it never changes a prescription on its own. Safe to rerun.
create table if not exists app.pharmacy_imports (
  id text primary key,
  organisation_id text not null references app.organisations,
  filename text not null,
  source text not null default 'upload' check (source in ('upload', 'webhook', 'poll')),
  rows int not null,
  matched int not null,
  as_of timestamptz not null,
  imported_by text references app.users,
  created_at timestamptz not null default now()
);

create table if not exists app.pharmacy_stock (
  organisation_id text not null references app.organisations,
  item_code text not null,
  item_name text not null,
  product_id text,
  product_label text,
  composition text,
  form text,
  match_state text not null check (match_state in ('matched', 'added', 'unmatched')),
  match_score real,
  quantity int not null,
  reorder_level int not null default 0,
  as_of timestamptz not null,
  import_id text not null references app.pharmacy_imports,
  primary key (organisation_id, item_code)
);
create index if not exists pharmacy_stock_product on app.pharmacy_stock (organisation_id, product_id);

alter table app.pharmacy_imports enable row level security;
alter table app.pharmacy_stock enable row level security;
