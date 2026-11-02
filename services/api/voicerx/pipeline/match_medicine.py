"""Catalog resolution on complete tokens; fuzzy candidates require review."""
import re
from decimal import Decimal
from typing import Literal
from rapidfuzz.fuzz import ratio
from ..contracts.medication import Strict
from .numbers import words_to_digits


class MatchResult(Strict):
    match: Literal['exact', 'ambiguous', 'unmatched']
    product_id: str | None
    candidate_ids: list[str]
    fuzzy: bool = False


def name_tokens(text):
    text = words_to_digits(text).replace('-', ' ')
    text = re.sub(r'(\d)([a-z])', r'\1 \2', text)
    ignored = {'tablet', 'tablets', 'tab', 'capsule', 'cap', 'inhaler', 'syrup', 'mg', 'mcg', 'ml'}
    return [t for t in text.split() if t not in ignored]


def match_medicine(spoken, products, current_ids=frozenset()):
    tokens = name_tokens(spoken)
    if not tokens:
        return MatchResult(match='unmatched', product_id=None, candidate_ids=[])
    names = {p.id: [name_tokens(n) for n in [p.brand, *p.aliases]] for p in products.values()}
    group = [pid for pid, ns in names.items() if any(n and n[0] == tokens[0] for n in ns)]
    fuzzy = not bool(group)
    if fuzzy:
        group = [pid for pid, ns in names.items() if any(n and ratio(n[0], tokens[0]) >= 85 for n in ns)]
    scores = {}
    extra = set(tokens[1:])
    for pid in group:
        strengths = {str(Decimal(c.strength).normalize()) for c in products[pid].components}
        strengths |= {c.strength for c in products[pid].components}
        for name in names[pid]:
            if not name or (name[0] != tokens[0] and not (fuzzy and ratio(name[0], tokens[0]) >= 85)):
                continue
            remaining = set(name[1:])
            if extra <= remaining | strengths:
                score = 3 if remaining == extra else 2 if remaining < extra else 1
                scores[pid] = max(scores.get(pid, 0), score)
    if not scores:
        return MatchResult(match='unmatched', product_id=None, candidate_ids=[])
    best = max(scores.values())
    candidates = sorted(pid for pid, score in scores.items() if score == best)
    chosen = None
    if not fuzzy:
        if len(candidates) == 1 and (best != 1 or len(group) == 1):
            chosen = candidates[0]
        elif len(candidates) > 1 and len(set(candidates) & current_ids) == 1:
            chosen = next(iter(set(candidates) & current_ids))
    return MatchResult(match='exact' if chosen else 'ambiguous', product_id=chosen,
                       candidate_ids=candidates, fuzzy=fuzzy)
