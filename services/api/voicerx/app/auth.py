"""Server-side sessions behind an HttpOnly cookie, with a CSRF token for every unsafe request (DESIGN.md 4.1).

Identity comes only from the session row: the browser never names its doctor or organisation.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets

from .db import one

COOKIE = 'vrx_session'
LIFETIME = timedelta(hours=12)
UNSAFE = {'POST', 'PUT', 'PATCH', 'DELETE'}


class NotSignedIn(Exception):
    pass


class Forbidden(Exception):
    pass


def _hash(token):
    return sha256(token.encode('utf-8')).hexdigest()


def create_session(conn, user_id, organisation_id):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    conn.execute('insert into app.sessions (token_hash, user_id, organisation_id, csrf_token, expires_at) '
                 'values (%s, %s, %s, %s, %s)',
                 (_hash(token), user_id, organisation_id, csrf, datetime.now(timezone.utc) + LIFETIME))
    return token


def end_session(conn, token):
    conn.execute('update app.sessions set revoked_at = now() where token_hash = %s', (_hash(token),))


def load_session(conn, token):
    if not token:
        raise NotSignedIn()
    row = one(conn, '''
        select s.user_id, s.organisation_id, s.csrf_token, s.expires_at, u.display_name, u.registration_no,
               u.specialty, u.synthetic, m.role, o.name as organisation_name, o.timezone
        from app.sessions s
        join app.users u on u.id = s.user_id
        join app.memberships m on m.user_id = s.user_id and m.organisation_id = s.organisation_id
        join app.organisations o on o.id = s.organisation_id
        where s.token_hash = %s and s.revoked_at is null and s.expires_at > now()''', (_hash(token),))
    if row is None:
        raise NotSignedIn()
    return row


def check_request(session, method, csrf_header, origin, allowed_origins):
    """Unsafe requests must carry the session's CSRF token and, when the browser sends one, an allowed Origin."""
    if method not in UNSAFE:
        return
    if not csrf_header or not secrets.compare_digest(csrf_header, session['csrf_token']):
        raise Forbidden('missing or wrong CSRF token')
    if origin and origin not in allowed_origins:
        raise Forbidden('request from an origin that is not allowed')


def session_view(session):
    return {
        'actor': {'id': session['user_id'], 'display_name': session['display_name'],
                  'registration_no': session['registration_no'], 'specialty': session['specialty'],
                  'synthetic': session['synthetic']},
        'scope': {'organisation_id': session['organisation_id'], 'organisation_name': session['organisation_name'],
                  'timezone': session['timezone'], 'role': session['role']},
        'capabilities': capabilities(session),
        'csrf_token': session['csrf_token'],
        'expires_at': session['expires_at'].isoformat(),
    }


def capabilities(session):
    clinical = session['role'] == 'doctor'
    return {'capture': clinical, 'resolve': clinical, 'approve': clinical, 'knowledge': clinical}


def require(session, capability):
    if not capabilities(session).get(capability):
        raise Forbidden(f'this role may not {capability}')
