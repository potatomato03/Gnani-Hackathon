-- Each run belongs to the deployment that created it, and only that deployment's worker takes it (runbook D-132).
-- A run with a pool keeps not_before and lease_until at the year 9000 (Python cannot read 'infinity'), so a
-- worker from before this change, which claims on those two columns, never sees it; pooled workers use due_at and pool_lease_until instead.
alter table app.runs add column if not exists pool text;
alter table app.runs add column if not exists due_at timestamptz;
alter table app.runs add column if not exists pool_lease_until timestamptz;
create index if not exists runs_pool_claim_idx on app.runs (pool, state, due_at);
