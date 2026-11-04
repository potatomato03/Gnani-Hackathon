import base64
import json

DEFAULT_MODEL = 'gemini-3.8-flash'


class GeminiAdapter:
    name = 'gemini'
    supports_attachments = True     # inline image and PDF parts (Interactions API docs, read 4 Nov 2026)

    def __init__(self, model=DEFAULT_MODEL):
        self.model = model

    def build(self, system, user, schema, key, attachments=()):
        parts = [{'type': 'text', 'text': system + '\n\n' + user}]
        parts += [{'type': 'document' if mime == 'application/pdf' else 'image',
                   'data': base64.b64encode(data).decode('ascii'), 'mime_type': mime} for mime, data in attachments]
        return ('https://generativelanguage.googleapis.com/v1beta/interactions',
                {'Content-Type': 'application/json', 'x-goog-api-key': key},
                {'model': self.model, 'input': [{'type': 'user_input', 'content': parts}],
                 'response_format': {'type': 'text', 'mime_type': 'application/json', 'schema': schema}})

    def reply_text(self, body):
        found = []
        for step in body.get('steps', []):
            if step.get('type') == 'model_output':
                for part in step.get('content', []):
                    if part.get('type') == 'text':
                        text = part.get('text', '')
                        try:
                            json.loads(text)
                            found.append(text)
                        except ValueError:
                            pass
        if not found:
            raise ValueError('Gemini returned no complete JSON model output')
        return found[-1]

    def is_quota_exhausted(self, status, headers, text):
        return status == 429 and ('per day' in text.casefold() or 'perday' in text.casefold())
