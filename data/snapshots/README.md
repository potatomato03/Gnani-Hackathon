# Snapshots

`indian_products.json.gz` is the Indian product list for the medicine name index. It's built from the local
dataset by `python tools/knowledge/build_products_snapshot.py`, and it matches `public.indian_products`.

The file is git-ignored because the dataset's licence doesn't clearly allow republishing it. Build it, and copy
it into the deploy folder before `vercel deploy`. Without it the app reads the list from Postgres instead,
which is slower and uses Supabase egress (runbook D-144).
