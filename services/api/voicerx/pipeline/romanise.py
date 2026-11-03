"""English said in a Hinglish dictation but written in Devanagari (runbook C-72).

Prisma sometimes writes "वन कैप्सूल" for "one capsule" and "पैरासिटामोल" for "paracetamol". The schedule
parsers and the product matcher read English, so common loanwords are turned back into English first, and a
remaining Devanagari name is spelt out in Latin letters for matching. Hindi words themselves are left as they
are: the parsers already read them.
"""
import re

NUKTA = '\u093c'
# Dictation English as speech recognition writes it in Devanagari; nukta-free, matched as whole words.
LOANWORDS = {
    'वन': 'one', 'टू': 'two', 'थ्री': 'three', 'फोर': 'four', 'फाइव': 'five', 'सिक्स': 'six', 'सेवन': 'seven',
    'एट': 'eight', 'नाइन': 'nine', 'टेन': 'ten', 'हाफ': 'half',
    'टैबलेट': 'tablet', 'टैबलेट्स': 'tablets', 'टेबलेट': 'tablet', 'टेबलेट्स': 'tablets', 'कैप्सूल': 'capsule',
    'कैप्सूल्स': 'capsules', 'सिरप': 'syrup', 'ड्रॉप्स': 'drops', 'इंजेक्शन': 'injection', 'सैशे': 'sachet',
    'ब्रेकफास्ट': 'breakfast', 'लंच': 'lunch', 'डिनर': 'dinner', 'मॉर्निंग': 'morning', 'इवनिंग': 'evening',
    'नाइट': 'night', 'आफ्टरनून': 'afternoon', 'डेली': 'daily', 'डे': 'day', 'डेज': 'days', 'वीक': 'week',
    'वीक्स': 'weeks', 'मंथ': 'month', 'मंथ्स': 'months', 'बिफोर': 'before', 'आफ्टर': 'after', 'ओरली': 'orally',
    'टाइम्स': 'times', 'टाइम': 'time', 'मैक्सिमम': 'maximum', 'फॉर': 'for',
    # Gujarati script (runbook D-121).
    'વન': 'one', 'ટુ': 'two', 'થ્રી': 'three', 'ફોર': 'four', 'ફાઈવ': 'five', 'ટેબ્લેટ': 'tablet',
    'ટેબલેટ': 'tablet', 'કેપ્સ્યુલ': 'capsule', 'કેપ્સૂલ': 'capsule', 'સિરપ': 'syrup', 'બ્રેકફાસ્ટ': 'breakfast',
    'લંચ': 'lunch', 'ડિનર': 'dinner', 'ડેઈલી': 'daily', 'ડેલી': 'daily', 'ડેઝ': 'days', 'ડે': 'day',
    'બિફોર': 'before', 'આફ્ટર': 'after', 'ઓરલી': 'orally',
}
VOWELS = {'अ': 'a', 'आ': 'a', 'इ': 'i', 'ई': 'i', 'उ': 'u', 'ऊ': 'u', 'ऋ': 'ri', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o',
          'औ': 'au', 'ऑ': 'o', 'ऍ': 'e'}
# In loanwords the "ai" sign usually stands for the a of "pan" and "tablet".
SIGNS = {'ा': 'a', 'ि': 'i', 'ी': 'i', 'ु': 'u', 'ू': 'u', 'ृ': 'ri', 'े': 'e', 'ै': 'a', 'ो': 'o', 'ौ': 'au',
         'ॉ': 'o', 'ॅ': 'e'}
CONSONANTS = {'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'n', 'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh',
              'ञ': 'n', 'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n', 'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh',
              'न': 'n', 'प': 'p', 'फ': 'f', 'ब': 'b', 'भ': 'bh', 'म': 'm', 'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v',
              'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h'}
MARKS = {'ं': 'n', 'ँ': 'n', 'ः': 'h'}
VIRAMA = '्'
DEVANAGARI = re.compile(r'[\u0900-\u097f\u0a80-\u0aff]')
INDIC_WORD = r'[\u0900-\u097f\u0a80-\u0aff]+'
# Gujarati letters sit 0x180 after their Devanagari counterparts, so a Gujarati word is spelt via Devanagari.
GUJARATI_SHIFT = 0x180


def english_loanwords(text):
    """Each whole word in LOANWORDS turned back into English; everything else unchanged."""
    def swap(match):
        word = match.group().replace(NUKTA, '')
        return LOANWORDS.get(word, match.group())
    return re.sub(INDIC_WORD, swap, text)


def _devanagari(word):
    return ''.join(chr(ord(c) - GUJARATI_SHIFT) if 0x0a80 <= ord(c) <= 0x0aff else c for c in word)


def _spell(word):
    out, pending = [], False
    for char in _devanagari(word).replace(NUKTA, ''):
        if char in CONSONANTS:
            if pending:
                out.append('a')
            out.append(CONSONANTS[char])
            pending = True
        elif char in SIGNS:
            out.append(SIGNS[char])
            pending = False
        elif char == VIRAMA:
            pending = False
        else:
            if pending and char in MARKS:
                out.append('a')
            out.append(VOWELS.get(char) or MARKS.get(char, ''))
            pending = False
    # A word's last consonant carries no vowel when spoken ("डोलो" ends in o, "पैरासिटामोल" in l).
    return ''.join(out)


def romanise(text):
    """Loanwords back to English, then any other Devanagari word spelt in Latin letters: "डोलो कैप्सूल" ->
    "dolo capsule". Text without Devanagari is returned unchanged."""
    if not DEVANAGARI.search(text):
        return text
    return re.sub(INDIC_WORD, lambda m: _spell(m.group()), english_loanwords(text))
