"""Create the knowledge tables in Supabase and load the chunks, their vectors and the Indian products.

    python tools/knowledge/upload_supabase.py
    python tools/knowledge/upload_supabase.py --schema-only
    python tools/knowledge/upload_supabase.py --popularity-only

Uses SUPABASE_DB_URL from the repo's .env. Each run replaces the tables' contents, so
it can be rerun after the chunks or vectors change. Only the brand list's identity
columns are loaded, never its description, side-effect or interaction text (D-95).
--popularity-only fills just the products' popularity, without reloading anything.
"""
import csv
import json
import math
import sys
import time
from pathlib import Path

from embed_chunks import CHUNK_FILES, DATA_DIR, MODEL, load_embeddings
from names import ingredients_of, product_composition

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
CHUNK_COLUMNS = ('id', 'source', 'label_id', 'title', 'section', 'part', 'parts', 'ingredients', 'route',
                 'classes', 'content', 'url', 'date', 'licence', 'note', 'embedding')
PRODUCT_COLUMNS = ('id', 'name', 'manufacturer', 'pack', 'composition', 'ingredients', 'popularity')
PRODUCTS = DATA_DIR / 'formulary/indian_medicine_dataset/updated_indian_medicine_data.csv'


def vector_literal(vector):
    """pgvector's text form. Five decimals are finer than half precision keeps."""
    return '[' + ','.join(f'{x:.5f}' for x in vector.tolist()) + ']'


def label_id(chunk):
    """openFDA ids are "<set_id>:<field>:<n>"; NLEM and Jan Aushadhi ids end in ":<n>"."""
    if chunk['source'] == 'openfda_label':
        return chunk['id'].split(':', 1)[0]
    return chunk['id'].rsplit(':', 1)[0]


def chunk_rows(chunks, ids, vectors):
    position = {chunk_id: index for index, chunk_id in enumerate(ids)}
    for chunk in chunks:
        vector = vectors[position[chunk['id']]]
        yield (chunk['id'], chunk['source'], label_id(chunk), chunk['title'], chunk['section'], chunk['part'],
               chunk['parts'], chunk['ingredients'], chunk.get('route'), chunk.get('classes'), chunk['text'],
               chunk.get('url'), chunk.get('date'), chunk.get('licence'), chunk.get('note'), vector_literal(vector))


def popularity(rows):
    """0 to 1 per product id from the list's order. Each first letter's products are listed best-selling
    first (PAN 40 2nd and Pan-D 3rd of 9,258 under "P"; runbook C-66), so the first gets 1 and the rest fall
    off with the log of their rank. Discontinued products keep their place but get 0. Inferred from the
    order, not stated by the dataset."""
    ranks, totals = {}, {}
    for row in rows:
        letter = row['name'].strip()[:1].lower()
        totals[letter] = totals.get(letter, 0) + 1
        ranks[int(row['id'])] = (letter, totals[letter], row['Is_discontinued'] == 'TRUE')
    return {pid: 0.0 if gone else round(1 - math.log(rank) / math.log(totals[letter] + 1), 3)
            for pid, (letter, rank, gone) in ranks.items()}


def product_rows(rows):
    rows = list(rows)
    scores = popularity(rows)
    for row in rows:
        if row['Is_discontinued'] == 'TRUE' or row['type'] != 'allopathy':
            continue
        composition = product_composition(row)
        yield (int(row['id']), row['name'].strip(), row['manufacturer_name'].strip() or None,
               row['pack_size_label'].strip() or None, composition, sorted(ingredients_of(composition)),
               scores[int(row['id'])])


def read_env(path):
    return dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines()
                if '=' in line and not line.startswith('#'))


def copy(conn, table, columns, rows):
    count = 0
    with conn.cursor().copy(f"copy public.{table} ({', '.join(columns)}) from stdin") as writer:
        for row in rows:
            writer.write_row(row)
            count += 1
    return count


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    import psycopg
    url = read_env(REPO_ROOT / '.env')['SUPABASE_DB_URL']
    if '--popularity-only' in sys.argv[1:]:
        return fill_popularity(psycopg, url)
    ids, vectors, meta = load_embeddings(DATA_DIR / 'knowledge/embeddings' / MODEL.split('/')[-1])
    chunks = [json.loads(line) for name in CHUNK_FILES
              for line in (DATA_DIR / 'knowledge/chunks' / name).open(encoding='utf-8')]
    if len(chunks) != len(ids):
        raise SystemExit(f'{len(chunks)} chunks but {len(ids)} vectors: rerun embed_chunks.py first')
    if '--schema-only' in sys.argv[1:]:
        # Re-create the tables' definitions and the search function, keeping the loaded data.
        with psycopg.connect(url, connect_timeout=30) as conn:
            conn.execute((HERE / 'schema.sql').read_text(encoding='utf-8'))
        print('schema applied')
        return 0
    with psycopg.connect(url, connect_timeout=30) as conn:
        conn.execute("set statement_timeout = 0")
        # A parallel index build ran the free plan out of shared memory; one worker with less memory fits.
        conn.execute("set maintenance_work_mem = '64MB'")
        conn.execute('set max_parallel_maintenance_workers = 0')
        conn.execute((HERE / 'schema.sql').read_text(encoding='utf-8'))
        conn.execute('truncate public.knowledge_chunks, public.indian_products')
        for index in ('knowledge_chunks_embedding_idx', 'knowledge_chunks_fts_idx', 'knowledge_chunks_ingredients_idx',
                      'knowledge_chunks_label_idx', 'indian_products_name_idx', 'indian_products_ingredients_idx'):
            conn.execute(f'drop index if exists public.{index}')
        started = time.time()
        count = copy(conn, 'knowledge_chunks', CHUNK_COLUMNS, chunk_rows(chunks, ids, vectors))
        print(f'knowledge_chunks: {count} rows in {time.time() - started:.0f}s', flush=True)
        with PRODUCTS.open(encoding='utf-8') as handle:
            started = time.time()
            count = copy(conn, 'indian_products', PRODUCT_COLUMNS, product_rows(csv.DictReader(handle)))
        print(f'indian_products: {count} rows in {time.time() - started:.0f}s', flush=True)
        started = time.time()
        conn.execute((HERE / 'indexes.sql').read_text(encoding='utf-8'))
        print(f'indexes built in {time.time() - started:.0f}s', flush=True)
        conn.commit()
        for table in ('knowledge_chunks', 'indian_products'):
            size = conn.execute(f"select pg_size_pretty(pg_total_relation_size('public.{table}'))").fetchone()[0]
            print(f'{table}: {size} with indexes', flush=True)
        print('database:', conn.execute('select pg_size_pretty(pg_database_size(current_database()))').fetchone()[0])
    return 0


def fill_popularity(psycopg, url):
    with PRODUCTS.open(encoding='utf-8') as handle:
        scores = popularity(csv.DictReader(handle))
    with psycopg.connect(url, connect_timeout=30) as conn:
        conn.execute('alter table public.indian_products add column if not exists popularity real')
        conn.execute('create temporary table ranked (id int primary key, popularity real) on commit drop')
        with conn.cursor().copy('copy ranked (id, popularity) from stdin') as writer:
            for row in scores.items():
                writer.write_row(row)
        count = conn.execute('update public.indian_products p set popularity = r.popularity from ranked r '
                             'where r.id = p.id').rowcount
        conn.commit()
    print(f'popularity set on {count} products')
    return 0


if __name__ == '__main__':
    sys.exit(main())
