"""Write the Indian product list for the app's name index to data/snapshots/indian_products.json.gz.

    python tools/knowledge/build_products_snapshot.py

Built from the same CSV and the same row rules as upload_supabase.py, so it matches public.indian_products.
The app loads it at start instead of reading all 246k rows from Postgres, which is fast and uses no Supabase
egress (runbook D-144). The file is git-ignored because the dataset's licence doesn't clearly allow
republishing it; add it to the deploy copy before `vercel deploy`. Without it the app reads Postgres, as before.
"""
import csv
import gzip
import json
import sys

from upload_supabase import PRODUCTS, REPO_ROOT, product_rows

OUT = REPO_ROOT / 'data/snapshots/indian_products.json.gz'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    with PRODUCTS.open(encoding='utf-8') as handle:
        # product_rows yields (id, name, manufacturer, pack, composition, ingredients, popularity).
        rows = [[pid, name, composition, manufacturer, popularity]
                for pid, name, manufacturer, _pack, composition, _ingredients, popularity
                in product_rows(csv.DictReader(handle))]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(gzip.compress(json.dumps({'count': len(rows), 'rows': rows}, ensure_ascii=False).encode('utf-8')))
    print(f'{len(rows)} products -> {OUT.relative_to(REPO_ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
