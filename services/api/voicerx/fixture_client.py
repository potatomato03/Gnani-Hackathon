"""A model client that replays saved stage outputs, so a case runs offline through the real checks."""
import json
from pathlib import Path


class FixtureClient:
    def __init__(self, directory, mutate=None):
        self.directory, self.mutate = Path(directory), mutate

    def generate(self, system, user, schema, prompt_version):
        from .llm.client import CallMeta
        name = 'extraction' if prompt_version.startswith('extract') else 'report_fields'
        data = json.loads((self.directory / (name + '.json')).read_text(encoding='utf-8'))
        if self.mutate:
            data = self.mutate(prompt_version, data)
        return schema.model_validate(data), CallMeta(provider='fixture', model='fixture',
            prompt_version=prompt_version, cache_key=name, cached=True, key_index=0, attempts=0)
