"""Small, deterministic multilingual number vocabulary for dictated values."""
import re
import unicodedata

NUMBERS = {}
for words in [
    'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen',
    'शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस',
    'సున్నా ఒకటి రెండు మూడు నాలుగు ఐదు ఆరు ఏడు ఎనిమిది తొమ్మిది పది',
    'பூஜ்ஜியம் ஒன்று இரண்டு மூன்று நான்கு ஐந்து ஆறு ஏழு எட்டு ஒன்பது பத்து',
]:
    NUMBERS.update({unicodedata.normalize('NFC', word): i for i, word in enumerate(words.split())})
NUMBERS.update(dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10))))
NUMBERS.update(dict(zip('बीस तीस चालीस पचास साठ सत्तर अस्सी नब्बे'.split(), range(20, 100, 10))))
NUMBERS.update({'ఒక': 1, 'ஒரு': 1, 'पांच': 5, 'छः': 6, 'पचानवे': 95, 'बानवे': 92,
                'अड़तालीस': 48, 'आधा': .5, 'आधी': .5, 'half': .5, 'डेढ़': 1.5, 'ढाई': 2.5,
                'hundred': 100, 'सौ': 100, 'point': '.', 'दशमलव': '.'})
VOCAB = '|'.join(re.escape(w) for w in sorted(NUMBERS, key=len, reverse=True))
RUN = re.compile(r'(?<!\w)(?:' + VOCAB + r')(?!\w)(?:[\s-]+(?:' + VOCAB + r')(?!\w))*')


def _integer(values):
    if 100 in values:
        i = values.index(100)
        return (sum(values[:i]) or 1) * 100 + sum(values[i + 1:])
    if len(values) >= 2 and 0 < values[0] < 10 and values[1] >= 20:
        return values[0] * 100 + sum(values[1:])
    return sum(values)


def _replace(match):
    values = [NUMBERS[w] for w in re.split(r'[\s-]+', match.group())]
    if '.' in values:
        i = values.index('.')
        if i and i < len(values) - 1 and all(isinstance(v, int) and 0 <= v < 10 for v in values[i+1:]):
            return str(_integer(values[:i])) + '.' + ''.join(str(v) for v in values[i+1:])
        return match.group()
    if len(values) > 1 and all(0 <= v < 10 for v in values):
        return ' '.join(f'{v:g}' for v in values)
    return f'{_integer(values):g}'


def words_to_digits(text: str) -> str:
    return RUN.sub(_replace, unicodedata.normalize('NFC', text).casefold())
