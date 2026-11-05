"""Provision the two requested demo hospitals and a private shared login; no demo patients are seeded.

Run locally with --archive-demo. The generated password is written only to the ignored credentials folder.
Re-running keeps the existing password and encryption keys. Nothing is uploaded by this command.
"""
import json
from pathlib import Path
import secrets
import sys

from cryptography.fernet import Fernet
import psycopg
from psycopg.rows import dict_row

from .config import REPO_ROOT,read_env
from .db import audit
from .migrate import MIGRATIONS
from .private_access import password_hash

# The real demo hospitals are named only in the ignored .env (APP_PRIVATE_HOSPITALS="id=Name;id=Name"), never in
# this public repository; the defaults are placeholders.
DEFAULT_HOSPITALS=(('hospital-demo-a','Demo Hospital A'),('hospital-demo-b','Demo Hospital B'))


def hospitals(env):
    listed=[item.split('=',1) for item in env.get('APP_PRIVATE_HOSPITALS','').split(';') if '=' in item]
    return tuple((oid.strip(),name.strip()) for oid,name in listed if oid.strip() and name.strip()) or DEFAULT_HOSPITALS


def main():
    env=read_env();settings_path=REPO_ROOT/'.env'
    chosen=hospitals(env)
    updates={'APP_DEV_LOGIN':'0','APP_PRIVATE_WORKSPACE':'1',
             'APP_DATA_KEY':env.get('APP_DATA_KEY') or Fernet.generate_key().decode(),
             'APP_AUTH_HMAC_KEY':env.get('APP_AUTH_HMAC_KEY') or secrets.token_urlsafe(48)}
    lines=settings_path.read_text().splitlines()
    lines=[line for line in lines if line.split('=',1)[0] not in updates]
    settings_path.write_text('\n'.join(lines+[key+'='+value for key,value in updates.items()])+'\n',encoding='utf-8')
    with psycopg.connect(env['SUPABASE_DB_URL'],row_factory=dict_row,prepare_threshold=None) as conn:
        for path in sorted(MIGRATIONS.glob('*.sql')):
            conn.execute(path.read_text(encoding='utf-8'))
        if '--archive-demo' in sys.argv:
            ids=[item['id'] for item in conn.execute('select id from app.organisations where synthetic and id<>all(%s) and archived_at is null',
                                                   ([item[0] for item in chosen],)).fetchall()]
            if ids:
                backup=REPO_ROOT/'runs/private-workspace-backup';backup.mkdir(parents=True,exist_ok=True)
                (backup/'archived-organisations.json').write_text(json.dumps(ids),encoding='utf-8')
                conn.execute('update app.organisations set archived_at=now() where id=any(%s)',(ids,))
                conn.execute('update app.sessions set revoked_at=now() where organisation_id=any(%s)',(ids,))
                conn.execute("update app.runs set state='cancelled',lease_until=null where encounter_id in "
                             "(select id from app.encounters where organisation_id=any(%s)) and state in ('queued','running','retry_wait')",(ids,))
                conn.execute("update app.clinic_report_jobs set state='cancelled',error='Workspace archived' where organisation_id=any(%s) "
                             "and state in ('pending','waiting_for_window','waiting_for_artifact')",(ids,))
                conn.execute("update app.patient_deliveries set state='cancelled',error='Workspace archived' where followup_id in "
                             "(select id from app.followups where organisation_id=any(%s)) and state in "
                             "('pending','waiting_for_contact','waiting_for_window','waiting_for_artifact')",(ids,))
                audit(conn,None,None,'workspace.demo_archived','organisation',None,{'organisation_ids':ids,'permanent_deletion':False})
                print('Archived previous demo organisations:',len(ids))
        uid='workspace-demo-admin'
        conn.execute("insert into app.users(id,display_name,synthetic,workspace_admin) values(%s,'Demo administrator',true,true) "
                     'on conflict(id) do update set workspace_admin=true,disabled_at=null',(uid,))
        for oid,name in chosen:
            conn.execute('insert into app.organisations(id,name,synthetic) values(%s,%s,true) on conflict(id) '
                         'do update set name=excluded.name,archived_at=null',(oid,name))
            conn.execute("insert into app.memberships(user_id,organisation_id,role) values(%s,%s,'admin') on conflict do nothing",(uid,oid))
        existing=conn.execute('select user_id from app.login_accounts where user_id=%s',(uid,)).fetchone()
        if not existing:
            username='demo-admin';password=secrets.token_urlsafe(30)
            conn.execute('insert into app.login_accounts(username,user_id,password_hash) values(%s,%s,%s)',(username,uid,password_hash(password)))
            output=REPO_ROOT.parent/'credentials'/'private-demo-access.txt'
            output.write_text('Private demo workspace\nUsername: '+username+'\nPassword: '+password+
                              '\n\nShare only with the invited demo doctors. Never commit or post this password.\n',encoding='utf-8')
            print('Private credentials saved to',output)
        # Seed the technical Meta service window from actual previously verified inbound events only.
        conn.execute('insert into app.whatsapp_contact_windows(contact,last_inbound_at) '
                     'select contact,max(last_inbound_at) from app.patient_channels where last_inbound_at is not null group by contact '
                     'on conflict(contact) do update set last_inbound_at=greatest(app.whatsapp_contact_windows.last_inbound_at,excluded.last_inbound_at)')
        print('Hospitals ready:',', '.join(name for _,name in chosen))
    return 0


if __name__=='__main__':
    sys.exit(main())
