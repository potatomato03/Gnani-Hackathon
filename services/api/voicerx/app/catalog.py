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
# Among the rest, a widely sold brand leads an obscure one that sounds as close (Pan-D over a little-known
# sound-alike); popularity runs 0 to 1 from the dataset's own order (runbook C-66) and never outweighs a listing.
POPULAR_BONUS = 0.15
UNITS = r'(?:mg|mcg|g|ml|iu|%)'
SOUND = [('ph', 'f'), ('ck', 'k'), ('x', 'ks')]
LETTERS = str.maketrans({'b': 'p', 'm': 'p', 'c': 'k', 'q': 'k', 'g': 'k', 'd': 't', 'z': 's', 'j': 's', 'v': 'f',
                         'w': 'f'})
# How a letter sounds when a doctor says a brand's suffix: "Pan-D" is said "pan dee", and speech recognition
# writes it as one word. Endings that sound like "ee" are written 'i' on both sides of a comparison.
LETTER_SOUNDS = {'a': 'e', 'b': 'bi', 'c': 'si', 'd': 'di', 'e': 'i', 'f': 'ef', 'g': 'ji', 'h': 'ech', 'i': 'ai',
                 'j': 'je', 'k': 'ke', 'l': 'el', 'm': 'em', 'n': 'en', 'o': 'o', 'p': 'pi', 'q': 'kyu', 'r': 'ar',
                 's': 'es', 't': 'ti', 'u': 'yu', 'v': 'vi', 'w': 'dablyu', 'x': 'eks', 'y': 'wai', 'z': 'zed'}
EE_ENDING = re.compile(r'(?:ee|ie|ea|ey|i|y)\b')


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


def spoken_forms(stem):
    """A stem whose later words are letters, as those letters are said, apart and joined: 'pan d' ->
    ['pan di', 'pandi']. A short word with no vowel, or a single letter, after the brand counts as letters."""
    words = stem.split()
    letters = [len(w) == 1 or (len(w) <= 3 and not re.search('[aeiou]', w)) for w in words]
    if len(words) < 2 or not any(letters[1:]) or not all(re.fullmatch('[a-z]+', w) for w in words[1:]):
        return []
    said = [words[0]] + [''.join(LETTER_SOUNDS[c] for c in w) if is_letters else w
                         for w, is_letters in zip(words[1:], letters[1:])]
    return [' '.join(said), ''.join(said)]


def fold_endings(stem):
    return EE_ENDING.sub('i', stem)


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
    popularity: float = 0.0
    stem: str = field(init=False)
    key: str = field(init=False)
    spoken: list = field(init=False)
    numbers: set = field(init=False)

    def __post_init__(self):
        self.stem = brand_stem(self.name)
        self.key = sound_key(self.stem)
        self.spoken = [(form, sound_key(form)) for form in spoken_forms(self.stem)]
        self.numbers = strengths(self.name, self.composition)


def standing(entry):
    """What an entry's list adds to its sound score: a clinic listing, else how widely the brand sells."""
    return LISTED_BONUS if entry.tier in ('formulary', 'clinic') else POPULAR_BONUS * entry.popularity


@dataclass
class Candidate:
    entry: CatalogEntry
    score: float
    strength_match: bool | None  # None when nothing was said about strength


def similarity(heard, entry):
    """How closely an entry's name matches heard words: spelling and sound, equally weighted, 0 to 1."""
    stem = brand_stem(heard)
    if not stem:
        return 0.0
    key = sound_key(stem)
    score = (fuzz.ratio(stem, entry.stem) + fuzz.ratio(key, entry.key)) / 200
    if entry.spoken:
        # A spoken letter's spelling is a guess ("dee", "di", "y"), so "ee" endings are folded first.
        folded = fold_endings(stem)
        score = max(score, *((fuzz.ratio(folded, form) + fuzz.ratio(key, form_key)) / 200
                             for form, form_key in entry.spoken))
    return score


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
        # Each name is searched as written and, for letter suffixes, as said; `owners` maps a row to its entry.
        rows = [(i, stem, key) for i, e in enumerate(self.entries) for stem, key in [(e.stem, e.key), *e.spoken]]
        self.owners = [i for i, _, _ in rows]
        self.stems = [stem for _, stem, _ in rows]
        self.keys = [key for _, _, key in rows]
        self.by_id = {e.id: e for e in self.entries}

    def candidates(self, heard, limit=12):
        stem = brand_stem(heard)
        if not stem:
            return []
        key, numbers = sound_key(stem), strengths(heard)
        indexes = set()
        for query, choices in ((stem, self.stems), (fold_endings(stem), self.stems), (key, self.keys)):
            indexes |= {self.owners[row] for _, _, row in process.extract(query, choices, scorer=fuzz.ratio, limit=80)}
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
        # clinic's own lists and well-known brands lead here already, or dozens of near-identical names crowd
        # them out of the limit.
        found.sort(key=lambda c: (c.strength_match is not False, c.score + standing(c.entry)), reverse=True)
        return found[:limit]
