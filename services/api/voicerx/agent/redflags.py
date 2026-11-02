"""Rules-first warning signs (runbook D-108). A model may add to these, never remove one."""
from functools import lru_cache
from pathlib import Path

import yaml

from .text import find, negated, tokens

RULES = Path(__file__).resolve().parents[4] / 'data/rules/red_flags.yaml'


@lru_cache(maxsize=1)
def load_rules(path=RULES):
    return yaml.safe_load(Path(path).read_text(encoding='utf-8'))


def find_red_flags(text):
    words = tokens(text)
    fired = []
    for flag in load_rules()['flags']:
        phrases = [p for key, values in flag.items() if key != 'id' for p in values]
        if any(not negated(words, span, phrase) for phrase in phrases for span in find(words, phrase)):
            fired.append(flag['id'])
    return fired
