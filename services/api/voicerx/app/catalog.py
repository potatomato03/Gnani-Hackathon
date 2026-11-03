"""Products beyond the reviewed formulary, and sound-alike search over them (spec 2026-11-03, parts B and C).

Tiers show in the id: `p-…` the reviewed formulary (exact matches only, in the engine), `in-…` the Indian
Medicine Dataset (unverified), `cp-…` products a clinic added (pending review). Anything outside the
formulary is only ever a suggestion the doctor confirms.
"""
from dataclasses import dataclass, field
import re

from rapidfuzz import fuzz, process

from ..pipeline.numbers import words_to_digits
from ..reference import Component, Product

FORMS = {'tablet': 'tablet', 'tablets': 'tablet', 'tab': 'tablet', 'capsule': 'capsule', 'capsules': 'capsule',
         'cap': 'capsule', 'syrup': 'syrup', 'suspension': 'suspension', 'susp': 'suspension', 'injection': 'injection',
         'inj': 'injection', 'gel': 'gel', 'cream': 'cream', 'ointment': 'ointment', 'drops': 'drops', 'drop': 'drops',
         'solution': 'solution', 'spray': 'spray', 'inhaler': 'inhaler', 'rotacap': 'inhaler', 'rotacaps': 'inhaler',
         'respules': 'inhaler', 'lotion': 'lotion', 'powder': 'powder', 'sachet': 'sachet', 'granules': 'granules',
         'kit': 'kit', 'strip': 'strip'}
# Release words describe the tablet, not the brand; "DS", "Plus", "Forte", "D" and "LC" tell products apart and stay.
RELEASE = {'sr', 'er', 'xr', 'cr', 'mr', 'pr', 'dt', 'ir'}
# The clinic's reviewed formulary and its own products are what this doctor is likely to prescribe; among
# near-identical sound-alikes in a 246,000-product list they lead (first measurement, 3 Nov).
LISTED_BONUS = 0.15
UNITS = r'(?:mg|mcg|g|ml|iu|%)'
SOUND = [('ph', 'f'), ('ck', 'k'), ('x', 'ks')]
LETTERS = str.maketrans({'b': 'p', 'm': 'p', 'c': 'k', 'q': 'k', 'g': 'k', 'd': 't', 'z': 's', 'j': 's', 'v': 'f',
                         'w': 'f'})


def parse_composition(text):
    components = []
    for part in re.split(r'\s\+\s', ' '.join((text or '').split())):
        match = re.match(r'^(.+?)\s*\(\s*([\d.]+)\s*([^)]*)\)\s*$', part)
        if match:
            components.append(Component(ingredient=match[1].strip(), strength=match[2], unit=match[3].strip().lower()))
        elif part.strip():
            components.append(Component(ingredient=part.strip(), strength='', unit=''))
    return components


def product_from_row(product_id, name, manufacturer, composition, form=None):
    words = name.split()
    kept = [w for w in words if w.lower() not in FORMS and w.lower() not in RELEASE]
    found = next((FORMS[w.lower()] for w in words if w.lower() in FORMS), None)
    return Product(id=product_id, brand=' '.join(kept) or name, manufacturer=manufacturer or 'not stated',
                   form=form or found or 'other', release_type='not_stated', components=parse_composition(composition),
                   aliases=[])


def brand_stem(name):
    """The brand's words without forms, release words, strengths or punctuation: 'Pan-D Capsule PR' -> 'pan d'."""
    text = re.sub(r'\d+(?:\.\d+)?\s*' + UNITS + r'?\b', ' ', words_to_digits(name.lower()))
    words = re.sub(r'[^a-zऀ-ॿ ]+', ' ', text).split()
    return ' '.join(w for w in words if w not in FORMS and w not in RELEASE)


def sound_key(stem):
    """Fold the letters speech recognition confuses (m/p/b, k/c/q/g, t/d, s/z/j, f/v/w/ph). Each run of vowels
    becomes one 'a', so a name keeps its syllables, and a word's final vowel, often unheard, is dropped.
    'man', 'pan' and 'ban' share a key; 'pan d' does not; unrelated names no longer collapse together."""
    keys = []
    for word in stem.split():
        for old, new in SOUND:
            word = word.replace(old, new)
        word = re.sub(r'[aeiouy]+', 'a', word.translate(LETTERS))
        if len(word) > 3 and word.endswith('a'):
            word = word[:-1]
        keys.append(re.sub(r'(.)\1+', r'\1', word))
    return ' '.join(keys)


def strengths(*texts):
    return {n.rstrip('0').rstrip('.') if '.' in n else n
            for text in texts for n in re.findall(r'\d+(?:\.\d+)?', words_to_digits((text or '').lower()))}


@dataclass
class CatalogEntry:
    id: str
    name: str
    composition: str
    tier: str
    manufacturer: str = ''
    stem: str = field(init=False)
    key: str = field(init=False)
    numbers: set = field(init=False)

    def __post_init__(self):
        self.stem = brand_stem(self.name)
        self.key = sound_key(self.stem)
        self.numbers = strengths(self.name, self.composition)


@dataclass
class Candidate:
    entry: CatalogEntry
    score: float
    strength_match: bool | None  # None when nothing was said about strength


def similarity(heard, entry):
    """How closely an entry's name matches heard words: spelling and sound, equally weighted, 0 to 1."""
    stem = brand_stem(heard)
    return (fuzz.ratio(stem, entry.stem) + fuzz.ratio(sound_key(stem), entry.key)) / 200 if stem else 0.0


class NameIndex:
    MIN_SCORE = 0.6

    def __init__(self, entries):
        # Pack sizes repeat a product; one entry per name and composition is enough to suggest it.
        seen, self.entries = set(), []
        for entry in entries:
            marker = (entry.stem, entry.composition.lower())
            if entry.stem and marker not in seen:
                seen.add(marker)
                self.entries.append(entry)
        self.stems = [e.stem for e in self.entries]
        self.keys = [e.key for e in self.entries]

    def candidates(self, heard, limit=12):
        stem = brand_stem(heard)
        if not stem:
            return []
        key, numbers = sound_key(stem), strengths(heard)
        indexes = set()
        for query, choices in ((stem, self.stems), (key, self.keys)):
            indexes |= {index for _, _, index in process.extract(query, choices, scorer=fuzz.ratio, limit=80)}
        found = []
        for index in indexes:
            entry = self.entries[index]
            # Spelling and sound count equally: either alone let unrelated names score as perfect matches.
            score = similarity(heard, entry)
            if score < self.MIN_SCORE:
                continue
            match = None if not numbers else bool(numbers & entry.numbers)
            found.append(Candidate(entry, round(score, 3), match))
        # A stated strength that agrees ranks first; a disagreeing one is kept, marked, and ranked after. The
        # clinic's own lists lead here already, or dozens of near-identical names crowd them out of the limit.
        found.sort(key=lambda c: (c.strength_match is not False,
                                  c.score + (LISTED_BONUS if c.entry.tier in ('formulary', 'clinic') else 0)), reverse=True)
        return found[:limit]
