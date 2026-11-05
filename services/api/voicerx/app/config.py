"""Settings from the repo's ignored .env. Keys arrive there from ../credentials via tools/credentials/sync_env.py."""
from dataclasses import dataclass
from pathlib import Path
import os

REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    database_url: str
    # Development sign-in: pick a synthetic seeded doctor, no password. Off unless set (runbook D-105).
    dev_login: bool
    artifacts_dir: Path
    llm_provider: str | None
    allowed_origins: tuple[str, ...]


def today_in(timezone_name):
    """The calendar date at the clinic. Windows Python may lack a time-zone database, so India falls back to +05:30."""
    from datetime import datetime, timedelta, timezone
    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(timezone_name)
    except Exception:
        if timezone_name != 'Asia/Kolkata':
            raise
        zone = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(zone).date()


def read_env(path=REPO_ROOT / '.env'):
    values=dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines()
                if '=' in line and not line.lstrip().startswith('#')) if path.exists() else {}
    return {**values,**os.environ}


def load_settings(env=None):
    env = read_env() if env is None else env
    if not env.get('SUPABASE_DB_URL'):
        raise RuntimeError('SUPABASE_DB_URL is not set; run tools/credentials/sync_env.py')
    origins = tuple(o.strip() for o in env.get('APP_ALLOWED_ORIGINS', 'http://127.0.0.1:8000,http://localhost:8000').split(','))
    hosted=bool(env.get('VERCEL')) or env.get('APP_ENV')=='production'
    if hosted and env.get('APP_DEV_LOGIN')=='1':
        raise RuntimeError('Development sign-in is prohibited on hosted deployments.')
    if hosted and env.get('APP_PRIVATE_WORKSPACE')!='1':
        raise RuntimeError('Hosted deployments must enable the private workspace.')
    if hosted and (not env.get('APP_DATA_KEY') or not env.get('APP_AUTH_HMAC_KEY')):
        raise RuntimeError('Private access keys are required on hosted deployments.')
    return Settings(database_url=env['SUPABASE_DB_URL'], dev_login=env.get('APP_DEV_LOGIN', '') == '1' and not hosted,
                    artifacts_dir=Path(env.get('APP_ARTIFACTS_DIR', '/tmp/voicerx' if hosted else REPO_ROOT / 'runs/app')),
                    llm_provider=env.get('APP_LLM_PROVIDER') or 'groq', allowed_origins=origins)
