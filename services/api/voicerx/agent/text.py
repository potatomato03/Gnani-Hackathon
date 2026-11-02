"""Text helpers for patient messages: one normal form and whole-word phrase matching.

Folds what patients type inconsistently: case, nukta (ज़ / ज), chandrabindu (साँस / सांस), curly apostrophes.
This is looser than the pipeline's verbatim rule on purpose: it reads patient messages, it never checks quotes.
"""
import unicodedata

NUKTA, CHANDRABINDU, ANUSVARA = '़', 'ँ', 'ं'
NEGATION_BEFORE = {'no', 'not', 'never', 'without', "don't", 'dont', "didn't", "haven't", 'denies'}
NEGATION_AFTER = {'नहीं', 'नही', 'ना', 'न', 'nahi', 'nahin', 'nai', 'na'}


def normalise(text):
    text = unicodedata.normalize('NFD', text.replace('’', "'"))
    text = text.replace(NUKTA, '').replace(CHANDRABINDU, ANUSVARA)
    return unicodedata.normalize('NFC', text).casefold()


def tokens(text):
    out, word = [], []
    for char in normalise(text):
        if unicodedata.category(char)[0] in 'LMN' or char == "'":
            word.append(char)
        elif word:
            out.append(''.join(word))
            word = []
    if word:
        out.append(''.join(word))
    return out


def find(text_tokens, phrase):
    """Spans (start, end) where the phrase's words appear in order. The last word may be a stem
    (फूल matches फूली, behosh matches behoshi); the others must match whole."""
    words = tokens(phrase)
    if not words:
        return []
    spans = []
    for i in range(len(text_tokens) - len(words) + 1):
        window = text_tokens[i:i + len(words)]
        if window[:-1] == words[:-1] and (window[-1] == words[-1] or (
                len(words[-1]) >= 3 and window[-1].startswith(words[-1]))):
            spans.append((i, i + len(words)))
    return spans


def negated(text_tokens, span, phrase):
    """True when a negation word stands right before (up to two words) or right after (up to two words) the
    phrase, unless the phrase itself carries the negation ("koi dikkat nahi")."""
    if set(tokens(phrase)) & (NEGATION_BEFORE | NEGATION_AFTER):
        return False
    start, end = span
    return bool(set(text_tokens[max(0, start - 2):start]) & NEGATION_BEFORE
                or set(text_tokens[end:end + 2]) & NEGATION_AFTER)


def contains(text, phrases):
    words = tokens(text)
    return any(find(words, p) for p in phrases)
