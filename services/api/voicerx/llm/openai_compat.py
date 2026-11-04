class OpenAICompatAdapter:
    """OpenAI-style chat completions with a strict JSON schema. Defaults to Groq; the same request shape
    serves other OpenAI-compatible providers by changing name, model and url."""

    def __init__(self, name='groq', model='openai/gpt-oss-120b',
                 url='https://api.groq.com/openai/v1/chat/completions'):
        self.name, self.model, self.url = name, model, url

    def build(self, system, user, schema, key):
        # Groq's edge refuses urllib's default User-Agent, so send our own.
        return self.url, {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                          'User-Agent': 'voicerx'}, {
            # Reasoning and the complete JSON share this budget. Leaving it unspecified rejected an
            # eight-minute consultation with json_validate_failed; that response needed 6,541 tokens.
            'model': self.model, 'temperature': 0, 'max_completion_tokens': 16384,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            'response_format': {'type': 'json_schema',
                                'json_schema': {'name': 'output', 'strict': True, 'schema': schema}}}

    def reply_text(self, body):
        choice = (body.get('choices') or [{}])[0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError('reply cut off before the end')
        text = choice.get('message', {}).get('content')
        if not isinstance(text, str):
            raise ValueError('provider returned no text')
        return text

    def is_quota_exhausted(self, status, headers, text):
        return status == 429 and 'per day' in text.casefold()

    def is_invalid_output(self, status, text):
        # The provider's own schema check refused what the model generated: worth one repair attempt.
        return status == 400 and 'json_validate_failed' in text
