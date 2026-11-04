"""Expose only Meta's webhook through a temporary tunnel; keep the doctor app private.

Run: python -m uvicorn voicerx.webhook_proxy:app --host 127.0.0.1 --port 8001 --no-access-log
The tunnel origin is port 8001, never the dashboard on port 8000.
"""
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
MAX_BYTES = 1024 * 1024
UPSTREAM = 'http://127.0.0.1:8000/whatsapp/webhook'


@app.api_route('/whatsapp/webhook', methods=['GET', 'POST'])
async def webhook(request: Request):
    data, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BYTES:
            return Response(status_code=413)
        data.append(chunk)
    headers = {key: request.headers[key] for key in ('content-type', 'x-hub-signature-256') if key in request.headers}
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.request(request.method, UPSTREAM, params=request.query_params,
                                            headers=headers, content=b''.join(data))
    except httpx.HTTPError:
        return Response(status_code=502)
    return Response(response.content, status_code=response.status_code,
                    media_type=response.headers.get('content-type', 'text/plain'))
