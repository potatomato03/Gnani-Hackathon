import httpx
from fastapi.testclient import TestClient

from voicerx import webhook_proxy


def test_proxy_does_not_expose_dashboard_or_any_api():
    client = TestClient(webhook_proxy.app)
    for path in ('/', '/api/v1/auth/dev-users', '/api/v1/followup/tasks', '/openapi.json', '/static/app.js'):
        assert client.get(path).status_code == 404


def test_proxy_preserves_signature_and_verification_query(monkeypatch):
    calls = []
    async def upstream(request):
        calls.append(request)
        return httpx.Response(200, text='challenge-or-ack')
    actual_client = httpx.AsyncClient
    monkeypatch.setattr(webhook_proxy.httpx, 'AsyncClient', lambda **kwargs: actual_client(transport=httpx.MockTransport(upstream)))
    client = TestClient(webhook_proxy.app)
    assert client.get('/whatsapp/webhook?hub.challenge=demo&hub.verify_token=fake').text == 'challenge-or-ack'
    assert calls[-1].url.params['hub.verify_token'] == 'fake'
    assert client.post('/whatsapp/webhook', content=b'{"entry":[]}', headers={
        'X-Hub-Signature-256': 'sha256=fake', 'Authorization': 'do-not-forward'}).status_code == 200
    assert calls[-1].headers['x-hub-signature-256'] == 'sha256=fake'
    assert 'authorization' not in calls[-1].headers
    assert calls[-1].content == b'{"entry":[]}'


def test_proxy_caps_body_size():
    assert TestClient(webhook_proxy.app).post('/whatsapp/webhook', content=b'x' * (webhook_proxy.MAX_BYTES + 1)).status_code == 413
