class OllamaAdapter:
    name = 'ollama'

    def __init__(self, model='qwen3:8b', host='http://localhost:11434'):
        self.model, self.host = model, host.rstrip('/')
        self.num_ctx = 8192

    def build(self, system, user, schema, key):
        return self.host + '/api/chat', {'Content-Type': 'application/json'}, {
            'model': self.model, 'stream': False, 'think': False, 'format': schema,
            # A looping reply stops at 4,096 tokens, is rejected as cut off, and gets one repair attempt.
            'options': {'temperature': 0, 'num_ctx': self.num_ctx, 'num_predict': 4096},
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}

    def reply_text(self, body):
        if body.get('done_reason') != 'stop' or body.get('prompt_eval_count', 0) + body.get('eval_count', 0) >= self.num_ctx:
            raise ValueError('Ollama reply truncated or context capacity reached')
        text = body.get('message', {}).get('content')
        if not isinstance(text, str):
            raise ValueError('Ollama returned no text')
        return text

    def is_quota_exhausted(self, status, headers, text):
        return status == 404
