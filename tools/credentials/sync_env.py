"""Copy the API keys from the credentials folder into the repo's ignored .env, never printing them.

    python tools/credentials/sync_env.py

The credentials folder (../credentials, or $CREDENTIALS_DIR) holds one file per key,
as Aditya keeps them. The root folder is searched too, for files not moved yet.
The database connection string is cleaned on the way: Supabase's template brackets
around the password are dropped and the password is URL-encoded (runbook D-104).
"""
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[2]
FOLDERS = [Path(os.environ.get('CREDENTIALS_DIR', REPO_ROOT.parent / 'credentials')), REPO_ROOT.parent]
# File name -> .env variable. mistral_API.env.txt is left out: Mistral is dropped (runbook C-29).
FILES = {
    'GNANI_API.env.txt': 'GNANI_API_KEY',
    'Gemini_API.env.txt': 'GEMINI_API_KEY',
    'Gemini_API(2).env.txt': 'GEMINI_API_KEY_2',
    'Groq_API.env.txt': 'GROQ_API_KEY',
    'Groq_API(2).env.txt': 'GROQ_API_KEY_2',
    'Supabase_API.env.txt': 'SUPABASE_ANON_KEY',
    'supabase_secret_key.env.txt': 'SUPABASE_SERVICE_ROLE_KEY',
    'database_connect_supabase.env.txt': 'SUPABASE_DB_URL',
}
DATABASE = re.compile(r'^(postgres(?:ql)?)://([^:]+):(.*)@([^@/:]+):(\d+)/(\w+)$')


def _password(raw):
    password = DATABASE.match(raw)[3]
    return password[1:-1] if password.startswith('[') and password.endswith(']') else password


def database_url(raw):
    _, user, _, host, port, db = DATABASE.match(raw).groups()
    return f"postgresql://{user}:{quote(_password(raw), safe='')}@{host}:{port}/{db}?sslmode=require"


def _read(name, folders):
    for folder in folders:
        path = Path(folder) / name
        if path.is_file():
            return path.read_text(encoding='utf-8-sig').strip()
    return None


def secret_values(folders=FOLDERS):
    """Every secret as it could appear in a file: each key, and the database password raw and encoded."""
    values = []
    for name in list(FILES) + ['mistral_API.env.txt']:
        value = _read(name, folders)
        if not value:
            continue
        values.append(value)
        if DATABASE.match(value):
            values += [_password(value), quote(_password(value), safe=''), database_url(value)]
    # Meta is supplied as a bundle. Read individual secrets without treating its non-secret settings
    # (model names, directories or recipient numbers) as keys, and never print the values.
    bundle = _read('meta_bot.env', folders)
    if bundle:
        meta = dict(line.split('=', 1) for line in bundle.splitlines()
                    if '=' in line and not line.lstrip().startswith('#'))
        for name in ('WHATSAPP_TOKEN', 'WHATSAPP_APP_SECRET', 'WHATSAPP_VERIFY_TOKEN', 'PATIENT_HASH_KEY'):
            value = meta.get(name, '').strip().strip('\"\'')
            if value:
                values.append(value)
    return values


def sync(env_path, folders=FOLDERS):
    lines = Path(env_path).read_text(encoding='utf-8').splitlines() if Path(env_path).exists() else []
    values = {variable: _read(name, folders) for name, variable in FILES.items()}
    if values['SUPABASE_DB_URL']:
        # The pooler user is "postgres.<project ref>", so the project URL can't drift from the database.
        ref = DATABASE.match(values['SUPABASE_DB_URL'])[2].removeprefix('postgres.')
        values['SUPABASE_URL'] = f'https://{ref}.supabase.co'
        values['SUPABASE_DB_URL'] = database_url(values['SUPABASE_DB_URL'])
    for variable, value in values.items():
        if value is None:
            print(f'{variable}: no file')
            continue
        line = f'{variable}={value}'
        at = next((i for i, l in enumerate(lines) if l.startswith(variable + '=')), None)
        if at is None:
            lines.append(line)
            print(f'{variable}: added')
        elif lines[at] != line:
            lines[at] = line
            print(f'{variable}: updated')
        else:
            print(f'{variable}: unchanged')
    Path(env_path).write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sync(REPO_ROOT / '.env')
