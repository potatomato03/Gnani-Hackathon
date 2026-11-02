"""A small connection pool for the app schema in Supabase Postgres."""
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

_pool = None


def open_pool(database_url):
    global _pool
    if _pool is None:
        # Each new connection costs a TLS handshake to the pooler; a few warm ones keep pages quick.
        _pool = ConnectionPool(database_url, min_size=2, max_size=8, open=True, timeout=30,
                               kwargs={'row_factory': dict_row, 'prepare_threshold': None})
    return _pool


def close_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def transaction():
    """One connection and one transaction: committed on success, rolled back on any error."""
    with _pool.connection() as conn:
        with conn.transaction():
            yield conn


def one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def all_rows(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def audit(conn, actor_id, organisation_id, action, entity, entity_id, detail=None):
    conn.execute('insert into app.audit_events (actor_id, organisation_id, action, entity, entity_id, detail) '
                 'values (%s, %s, %s, %s, %s, %s)', (actor_id, organisation_id, action, entity, entity_id, Jsonb(detail or {})))
