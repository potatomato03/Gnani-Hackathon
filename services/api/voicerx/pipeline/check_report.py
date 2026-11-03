"""Conservative report checks. These lexical checks are not semantic proof."""
from collections import Counter
import re
from .check_extraction import NEGATION_WORDS, SIDE_WORDS, has_word, issue, normalise
from .numbers import words_to_digits

SECTION_KINDS = {'chief_complaints': {'symptom'}, 'history_present_illness': {'symptom', 'history', 'family_history', 'allergy'},
                 'vitals': {'vital'}, 'examination': {'exam'}, 'investigation_results': {'result'},
                 'investigations_ordered': {'order'}, 'diagnoses': {'diagnosis'}, 'advice': {'advice'},
                 'referrals': {'referral'}, 'plan': {'plan'}, 'follow_up': {'follow_up'}}
NEGATION = {'no', 'not', 'denies', 'denied', 'negative', 'absent', 'nil', 'without', 'none'}
RELATIVES = {'family', 'mother', 'father', 'brother', 'sister', 'son', 'daughter', 'wife', 'husband', 'parent', 'relative'}
PROVISIONAL = {'provisional', 'suspected', 'probable', 'likely'}
PAST = {'history of', 'known', 'past', 'previous', 'earlier', 'since', 'ago'}


def numbers(text):
    return set(re.findall(r'\d+(?:\.\d+)?', words_to_digits(text)))


def check_report(fields, checked, reference):
    by_id = {item.id: item for item in checked.kept}
    used = Counter()
    issues = []
    names = {n for p in reference.products.values() for n in [p.brand, *p.aliases]}
    for section in SECTION_KINDS:
        for index, line in enumerate(getattr(fields, section)):
            target = f'{section}:{index}'
            cited = [by_id[c] for c in line.cites if c in by_id]
            used.update(set(c for c in line.cites if c in by_id))
            def flag(code, severity='block'):
                issues.append(issue(code, target, severity))
            if not line.cites or len(cited) != len(line.cites):
                flag('line_unsupported')
            text = normalise(line.text)
            source = ' '.join(x.term + ' ' + x.quote for x in cited)
            if not numbers(text) <= numbers(source):
                flag('number_not_in_source')
            if any(has_word(text, {name}) and not has_word(source, {name}) for name in names):
                flag('medicine_not_in_source')
            # A unit followed by "/" is a lab concentration ("160 mg/dL"), not a dose.
            if re.search(r'\b\d+(\.\d+)?\s?(mg|mcg|ml|tablets?|tabs?|capsules?|puffs?)\b(?!\s*/)', text):
                flag('dose_in_text')
            if not cited:
                continue
            assertions = {x.assertion for x in cited}
            negative = has_word(text, NEGATION)
            # One sentence may join present and absent findings ("sore throat for 3 days, no fever"), as
            # outpatient summaries do; each absent finding still needs its negative written.
            if 'absent' in assertions and not negative:
                flag('negation_mismatch')
            if 'unknown' in assertions and not has_word(text, {'unknown', 'uncertain', 'unclear', 'not recorded', 'not stated', 'not known'}):
                flag('negation_mismatch')
            if assertions == {'present'} and negative and not any(has_word(x.quote, NEGATION_WORDS) for x in cited):
                flag('negation_mismatch')
            relative = has_word(text, RELATIVES)
            if (any(x.subject != 'patient' for x in cited) and not relative) or (all(x.subject == 'patient' for x in cited) and relative):
                flag('subject_mismatch')
            if (any(x.certainty == 'provisional' for x in cited) and not has_word(text, PROVISIONAL)) or (
                any(x.certainty == 'rule_out' for x in cited) and 'rule out' not in text) or (
                all(x.certainty == 'stated' for x in cited) and has_word(text, PROVISIONAL | {'rule out'})):
                flag('certainty_mismatch')
            if any(x.temporality == 'past' for x in cited) and not has_word(text, PAST):
                flag('temporality_mismatch', 'warn')
            written_sides = {side for side, words in SIDE_WORDS.items() if has_word(text, words)}
            supported_sides = {x.laterality for x in cited if x.laterality} | {
                side for side, words in SIDE_WORDS.items() if any(has_word(x.quote, words) for x in cited)}
            if written_sides - supported_sides or any(x.laterality and not has_word(text, {'both', 'bilateral'} if x.laterality == 'bilateral' else {x.laterality}) for x in cited):
                flag('laterality_mismatch')
            if any(x.kind not in SECTION_KINDS[section] for x in cited):
                flag('section_mismatch', 'warn')
    for item in checked.kept:
        if used[item.id] == 0:
            issues.append(issue('omission', item.id))
        elif used[item.id] > 1:
            issues.append(issue('duplication', item.id, 'warn'))
    if not checked.kept and not checked.medications:
        issues.append(issue('nothing_extracted', 'report'))
    return issues
