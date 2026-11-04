from sync_env import database_url, secret_values, sync


def test_keys_are_copied_into_env_without_touching_other_lines(tmp_path, capsys):
    folder = tmp_path / 'credentials'
    folder.mkdir()
    (folder / 'GNANI_API.env.txt').write_text('gnani-secret-123\n', encoding='utf-8')
    (folder / 'Groq_API(2).env.txt').write_text('gsk_second\n', encoding='utf-8')
    env = tmp_path / '.env'
    env.write_text('# keep me\nGNANI_API_KEY=old\nOLLAMA_MODEL=qwen3:8b\n', encoding='utf-8')
    sync(env, [folder])
    assert env.read_text(encoding='utf-8') == ('# keep me\nGNANI_API_KEY=gnani-secret-123\nOLLAMA_MODEL=qwen3:8b\n'
                                               'GROQ_API_KEY_2=gsk_second\n')
    out = capsys.readouterr().out
    assert 'gnani-secret-123' not in out and 'gsk_second' not in out
    assert 'GNANI_API_KEY: updated' in out and 'GROQ_API_KEY_2: added' in out and 'GEMINI_API_KEY: no file' in out


def test_first_folder_wins(tmp_path):
    first, second = tmp_path / 'credentials', tmp_path / 'root'
    for folder, value in ((first, 'new'), (second, 'old')):
        folder.mkdir()
        (folder / 'GNANI_API.env.txt').write_text(value, encoding='utf-8')
    env = tmp_path / '.env'
    env.write_text('', encoding='utf-8')
    sync(env, [first, second])
    assert 'GNANI_API_KEY=new' in env.read_text(encoding='utf-8')


def test_database_url_drops_template_brackets_and_encodes_the_password():
    raw = 'postgresql://postgres.abc:[p@ss/word]@aws-1-eu-central-1.pooler.supabase.com:5432/postgres'
    assert database_url(raw) == ('postgresql://postgres.abc:p%40ss%2Fword@aws-1-eu-central-1.pooler.supabase.com'
                                 ':5432/postgres?sslmode=require')


def test_project_url_follows_the_database_connection(tmp_path, capsys):
    folder = tmp_path / 'credentials'
    folder.mkdir()
    (folder / 'database_connect_supabase.env.txt').write_text(
        'postgresql://postgres.newref123:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres', encoding='utf-8')
    env = tmp_path / '.env'
    env.write_text('SUPABASE_URL=https://oldref.supabase.co\n', encoding='utf-8')
    sync(env, [folder])
    assert 'SUPABASE_URL=https://newref123.supabase.co' in env.read_text(encoding='utf-8')
    assert 'SUPABASE_URL: updated' in capsys.readouterr().out


def test_secret_values_include_the_bare_database_password(tmp_path):
    folder = tmp_path / 'credentials'
    folder.mkdir()
    (folder / 'database_connect_supabase.env.txt').write_text(
        'postgresql://postgres.abc:[p@ss]@host.pooler.supabase.com:5432/postgres', encoding='utf-8')
    (folder / 'GNANI_API.env.txt').write_text('gnani', encoding='utf-8')
    assert {'gnani', 'p@ss', 'p%40ss'} <= set(secret_values([folder]))


def test_meta_bundle_secrets_are_scanned_without_treating_settings_as_secrets(tmp_path):
    (tmp_path / 'meta_bot.env').write_text(
        'WHATSAPP_TOKEN="fake-meta-token"\nWHATSAPP_APP_SECRET=fake-app-secret\n'
        'WHATSAPP_VERIFY_TOKEN=fake-verify-token\nPATIENT_HASH_KEY=fake-hash-key\n'
        'GROQ_MODEL=model-name\nWHATSAPP_TEST_NUMBERS=910000000001\n', encoding='utf-8')
    assert set(secret_values([tmp_path])) == {
        'fake-meta-token', 'fake-app-secret', 'fake-verify-token', 'fake-hash-key'}
