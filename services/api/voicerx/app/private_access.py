"""Private shared demo access. No public signup, account discovery, or browser credentials storage."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet

from .config import read_env
from .db import audit, one


def password_hash(password, salt=None):
    if not isinstance(password,str) or not 16<=len(password)<=200:
        raise ValueError('Use a password between 16 and 200 characters.')
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode(),salt=salt,n=32768,r=8,p=1,maxmem=64*1024*1024)
    return 'scrypt$'+base64.urlsafe_b64encode(salt).decode()+'$'+base64.urlsafe_b64encode(digest).decode()


def password_matches(password, encoded):
    try:
        scheme,salt,_=encoded.split('$')
        return scheme=='scrypt' and hmac.compare_digest(password_hash(password,base64.urlsafe_b64decode(salt)),encoded)
    except (ValueError,TypeError):
        return False


def encrypt_phone(number):
    return Fernet(read_env()['APP_DATA_KEY'].encode()).encrypt(number.encode()).decode()


def decrypt_phone(encrypted):
    return Fernet(read_env()['APP_DATA_KEY'].encode()).decrypt(encrypted.encode()).decode()


def authenticate(conn, username, password, ip):
    """Persisted rate limits work across instances; failures commit before the HTTP error is returned."""
    username=username.strip().casefold()
    secret=read_env().get('APP_AUTH_HMAC_KEY')
    if not secret:
        raise RuntimeError('Private sign-in has not been configured.')
    keys=[hmac.new(secret.encode(),value.encode(),hashlib.sha256).hexdigest()
          for value in ('user:'+username,'ip:'+ip)]
    current=datetime.now(timezone.utc)
    limits=[]
    for key in sorted(keys):
        conn.execute('insert into app.login_limits(key) values(%s) on conflict do nothing',(key,))
        row=one(conn,'select * from app.login_limits where key=%s for update',(key,))
        if row['blocked_until'] and row['blocked_until']>current:
            return None,True
        if current-row['window_started']>timedelta(minutes=15):
            conn.execute('update app.login_limits set attempts=0,window_started=now(),blocked_until=null where key=%s',(key,))
            row={**row,'attempts':0}
        limits.append(row)
    account=one(conn,'select a.* from app.login_accounts a join app.users u on u.id=a.user_id '
                'where a.username=%s and a.disabled_at is null and u.disabled_at is null',(username,))
    # Equal-cost password verification also for an unknown username.
    dummy='scrypt$'+base64.urlsafe_b64encode(b'private-demo-key').decode()+'$'+base64.urlsafe_b64encode(bytes(64)).decode()
    valid=password_matches(password,account['password_hash'] if account else dummy)
    if not account or not valid:
        for row in limits:
            attempts=row['attempts']+1
            conn.execute('update app.login_limits set attempts=%s,blocked_until=%s where key=%s',
                         (attempts,current+timedelta(minutes=15) if attempts>=8 else None,row['key']))
        audit(conn,None,None,'auth.login_failed','account',None)
        return None,False
    # The IP bucket is not reset by a successful account, preventing cross-account limit evasion.
    conn.execute('update app.login_limits set attempts=0,blocked_until=null where key=%s',(keys[0],))
    member=one(conn,'select m.organisation_id from app.memberships m join app.organisations o on o.id=m.organisation_id '
               'where m.user_id=%s and o.archived_at is null order by o.name limit 1',(account['user_id'],))
    return ({**account,**member} if member else None),False
