"""Staff reference search over the Supabase knowledge tables (DESIGN.md section 10).

Results are reference passages with their sources, shown beside the record; they never enter it.
"""
import sys
import threading

from .config import REPO_ROOT

MAX_QUESTION = 300
MAX_RESULTS = 8
MODEL = 'BAAI/bge-base-en-v1.5'
_model = None
_lock = threading.Lock()

# The ingredient map lives with the knowledge tools; one copy keeps app and tables in step.
sys.path.insert(0, str(REPO_ROOT / 'tools/knowledge'))
from names import ingredient_key  # noqa: E402


def stand_in_for_mmh3():
    """fastembed imports mmh3 only for BM25 sparse embeddings, which this app never uses. Where it can't load
    (Windows Application Control blocked its compiled file on 3 Nov, runbook C-69), a stand-in that refuses to
    hash lets the dense model load. The blocked file itself is never run."""
    try:
        import mmh3  # noqa: F401
    except ImportError:
        import types

        def unavailable(*args, **kwargs):
            raise RuntimeError('mmh3 could not load; sparse (BM25) embeddings are not used by this app')
        stub = types.ModuleType('mmh3')
        stub.hash = stub.hash64 = stub.hash128 = stub.hash_bytes = stub.hash_from_buffer = unavailable
        sys.modules['mmh3'] = stub


def _embedder():
    global _model
    with _lock:
        if _model is None:
            stand_in_for_mmh3()
            from fastembed import TextEmbedding
            _model = TextEmbedding(MODEL, cache_dir=str(REPO_ROOT.parent / 'models' / 'fastembed'))
    return _model


def warm_up():
    _embedder()


def ingredient_keys(product):
    return sorted({ingredient_key(c.ingredient) for c in product.components})


def search(conn, question, ingredients=None, limit=6):
    question = ' '.join(question.split())[:MAX_QUESTION]
    if not question:
        return []
    vector = next(iter(_embedder().query_embed([question])))
    literal = '[' + ','.join(f'{x:.5f}' for x in vector.tolist()) + ']'
    rows = conn.execute(
        'select id, source, title, section, content, url, similarity, score from public.match_chunks('
        '%s::extensions.halfvec, %s, %s, ingredients => %s)',
        (literal, question, min(limit, MAX_RESULTS), ingredients or None)).fetchall()
    def passage(row):
        # Label chunks open with "<medicine> (<route; class>). <section>: "; the screen shows those apart.
        marker = row['section'] + ': '
        at = row['content'].find(marker)
        return row['content'][at + len(marker):] if row['source'] == 'openfda_label' and at >= 0 else row['content']
    return [{**row, 'content': passage(row)} for row in rows]
