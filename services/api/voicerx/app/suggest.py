"""Suggestions for a medicine the matcher couldn't name exactly (spec 2026-11-03, part B).

Candidates come from sound and spelling; the visit's context and the knowledge base decide their order;
Groq writes the order and a short reason but may only use the candidates it is given. The doctor confirms
with a click: nothing here ever changes the draft.
"""
import logging
import re
import threading

from pydantic import Field

from ..contracts.medication import Strict
from ..pipeline.assemble import product_label
from . import knowledge
from .catalog import (Candidate, CatalogEntry, NameIndex, brand_stem, product_from_row, similarity, standing,
                      strengths)

log = logging.getLogger('voicerx.suggest')
PROMPT_VERSION = 'suggest-v3'
MAX_CANDIDATES = 8
MAX_SUGGESTIONS = 5
PRIOR_BONUS = 0.3
MODEL_BONUS = (0.15, 0.1, 0.05)
FIT_WEIGHT = 0.2
MISMATCH_PENALTY = 0.1
# A first suggestion is shown as "likely" only when its name sounds this close and no sound-alike sibling
# (Pan 40 beside Pan-D) is in the list; otherwise the doctor sees "possible matches" and picks.
CONFIDENT_SOUND = 0.8
# ...and no other suggestion sounds almost as close (several LC brands can sound equally close).
CONFIDENT_MARGIN = 0.05
# A brand this high in the dataset's sales order is told to the model as widely sold.
WIDELY_SOLD = 0.6
FIT_SECTIONS = ['Uses', 'Purpose', 'Essential medicine listing', 'Therapeutic group']
SYSTEM = (
    "A speech recogniser may have misheard a medicine name in a doctor's consultation. You get the words it "
    'wrote, the consultation context and candidate products whose names sound similar. Rank the candidates the '
    'doctor plausibly meant, best first. Rules, in order of weight: '
    '1. The name is the main evidence. Rank a candidate only if its brand name plausibly sounds like the heard '
    'words; never rank a product for its use alone. If no candidate name plausibly sounds like the heard words, '
    'return an empty list. '
    '2. The form must suit what was said: "before breakfast", "tablet" or "once a day" mean something taken by '
    'mouth, not an injection, cream or syrup for an adult unless said. '
    '3. Among equally close names, prefer products marked "in the clinic list", then well-known brands. '
    '4. Use the context (what it is for, the findings, the other medicines) to choose between close names. '
    '5. A stated strength that differs is a warning to mention, not a reason to prefer a worse-sounding name. '
    'Use only the candidate ids given; never invent one. Each reason is one short sentence naming the heard '
    'words and the context words that support it.')

_index, _lock = None, threading.Lock()


class Ranked(Strict):
    id: str
    reason: str = Field(max_length=240)


class Ranking(Strict):
    ranked: list[Ranked] = Field(max_length=MAX_CANDIDATES)


def composition_text(product):
    return ' + '.join(f'{c.ingredient} ({c.strength}{c.unit})' if c.strength else c.ingredient for c in product.components)


def heard_key(heard):
    """The same heard words always give the same key: brand stem plus any strengths."""
    return ' '.join([brand_stem(heard), *sorted(strengths(heard))]).strip()


def shared_index(conn, formulary):
    """Every product the clinic could mean: the formulary first, then the Indian Medicine Dataset."""
    global _index
    with _lock:
        if _index is None:
            entries = [CatalogEntry(p.id, f'{name} {p.form}', composition_text(p), 'formulary', p.manufacturer)
                       for p in formulary.values() for name in [p.brand, *p.aliases]]
            rows = conn.execute('select id, name, composition, manufacturer, coalesce(popularity, 0) as popularity '
                                'from public.indian_products').fetchall()
            entries += [CatalogEntry(f"in-{r['id']}", r['name'], r['composition'], 'indian', r['manufacturer'] or '',
                                     float(r['popularity'])) for r in rows]
            _index = NameIndex(entries)
    return _index


def clinic_index(conn, organisation_id):
    rows = conn.execute("select id, name, composition, manufacturer from app.clinic_products "
                        "where organisation_id = %s and status <> 'withdrawn'", (organisation_id,)).fetchall()
    return NameIndex([CatalogEntry(r['id'], r['name'], r['composition'], 'clinic', r['manufacturer'] or '') for r in rows])


def catalog_product(conn, organisation_id, product_id, formulary):
    """The Product for any tier's id, or None."""
    if product_id in formulary:
        return formulary[product_id]
    if product_id.startswith('in-') and product_id[3:].isdigit():
        row = conn.execute('select id, name, composition, manufacturer from public.indian_products where id = %s',
                           (int(product_id[3:]),)).fetchone()
        return product_from_row(product_id, row['name'], row['manufacturer'], row['composition']) if row else None
    if product_id.startswith('cp-'):
        row = conn.execute('select * from app.clinic_products where id = %s and organisation_id = %s',
                           (product_id, organisation_id)).fetchone()
        return product_from_row(product_id, row['name'], row['manufacturer'], row['composition'], row['form']) if row else None
    return None


def context_for(transcript, rx, checked):
    """The sentence around the heard name, the visit's findings and the other medicines."""
    text = ' '.join(transcript.split())
    at = text.lower().find(rx.quotes.get('name_quote', rx.spoken_name).lower())
    window = text[max(0, at - 160):at + 220] if at >= 0 else ''
    findings = [i.term for i in checked.kept if i.kind in ('symptom', 'diagnosis', 'exam', 'result', 'history')
                and i.assertion == 'present'][:12]
    others = [m.spoken_name for m in checked.medications if m.id != rx.id]
    return window, findings, others


def knowledge_of(conn, product, context_vector):
    keys = knowledge.ingredient_keys(product)
    if not keys:
        return {'class': None, 'category': None, 'fit': None}
    row = conn.execute("select classes from public.knowledge_chunks where source = 'openfda_label' and ingredients && %s "
                       "and coalesce(classes, '') <> '' limit 1", (keys,)).fetchone()
    nlem = conn.execute("select content from public.knowledge_chunks where source = 'nlem_2022' and ingredients && %s "
                        'limit 1', (keys,)).fetchone()
    fit = conn.execute('select max(1 - (embedding <=> %s::extensions.halfvec)) as fit from public.knowledge_chunks '
                       'where ingredients && %s and section = any(%s)', (context_vector, keys, FIT_SECTIONS)).fetchone()
    category = re.search(r'Listed under: (.+?)(?: \(level|\.)', nlem['content']) if nlem else None
    return {'class': row['classes'] if row else None, 'category': category[1] if category else None,
            'fit': round(float(fit['fit']), 3) if fit and fit['fit'] is not None else None}


def merge_ranking(candidate_ids, ranking):
    """The model's order and reasons, keeping only ids it was given; candidates it left out follow in their
    sound-alike order, without a reason."""
    reasons = {}
    for item in ranking.ranked if ranking else []:
        if item.id in candidate_ids and item.id not in reasons:
            reasons[item.id] = item.reason
    return list(reasons) + [pid for pid in candidate_ids if pid not in reasons], reasons


def suggest(conn, client, transcript, rx, checked, organisation_id, doctor_id, formulary):
    """Up to five suggestions for one medicine, best first, and how they were made."""
    heard = rx.spoken_name
    pools = [shared_index(conn, formulary), clinic_index(conn, organisation_id)]
    found = {}
    # A fixed order, and every candidate judged on strength against the full heard words: the bare quote
    # ("Band") carries no strength, and its results escaped the mismatch rule depending on set order.
    numbers = strengths(heard, rx.quotes.get('name_quote', ''))
    for name in dict.fromkeys([heard, rx.quotes.get('name_quote', heard)]):
        for pool in pools:
            # A wide net: a listed product must not be cut off before the bonus that lifts it is applied.
            for c in pool.candidates(name, limit=40):
                if c.entry.id not in found or c.score > found[c.entry.id].score:
                    found[c.entry.id] = Candidate(c.entry, c.score, bool(numbers & c.entry.numbers) if numbers else None)
    priors = {r['product_id']: r['times'] for r in conn.execute(
        'select product_id, times from app.medicine_aliases where organisation_id = %s and doctor_id = %s and heard_key = %s',
        (organisation_id, doctor_id, heard_key(heard))).fetchall()}
    ordered = sorted(found.values(), key=lambda c: (c.entry.id in priors, c.entry.id in rx.candidate_ids,
                                                    c.strength_match is not False, c.score + standing(c.entry)),
                     reverse=True)
    picked = []
    for candidate in ordered[:MAX_CANDIDATES]:
        product = catalog_product(conn, organisation_id, candidate.entry.id, formulary)
        if product:
            picked.append((candidate, product))
    # The doctor's earlier choices and the formulary's own candidates (a bare "Pan") are always offered.
    known = {c.entry.id for c, _ in picked}
    for pid in [*priors, *rx.candidate_ids]:
        product = catalog_product(conn, organisation_id, pid, formulary) if pid not in known else None
        if product:
            tier = 'formulary' if pid in formulary else 'clinic' if pid.startswith('cp-') else 'indian'
            entry = pools[0].by_id.get(pid) or CatalogEntry(pid, f'{product.brand} {product.form}',
                                                            composition_text(product), tier)
            # Scored like any other candidate, so a past choice that sounds less alike still gets its due.
            picked.append((Candidate(entry, round(similarity(heard, entry), 3),
                                     bool(numbers & entry.numbers) if numbers else None), product))
            known.add(pid)
    if not picked:
        return [], {'candidates': 0}
    window, findings, others = context_for(transcript, rx, checked)
    context_text = ' '.join([window, *findings]).strip() or heard
    vector = next(iter(knowledge._embedder().query_embed([context_text])))
    literal = '[' + ','.join(f'{x:.5f}' for x in vector.tolist()) + ']'
    facts = {c.entry.id: knowledge_of(conn, p, literal) for c, p in picked}
    lines = []
    for candidate, product in picked:
        fact = facts[candidate.entry.id]
        listed_note = ('; in the clinic list' if candidate.entry.tier in ('formulary', 'clinic')
                       else '; widely sold' if candidate.entry.popularity >= WIDELY_SOLD else '')
        lines.append(f'- id {candidate.entry.id}: {product_label(product)}; form {product.form}; contains '
                     f'{composition_text(product)}; class {fact["class"] or "unknown"}; '
                     f'listed as {fact["category"] or "unknown"}{listed_note}; '
                     f'sounds like the heard words {candidate.score:.2f}; '
                     f'strength {"agrees" if candidate.strength_match else "differs" if candidate.strength_match is False else "not said"}'
                     + ('; the doctor chose this for these words before' if candidate.entry.id in priors else ''))
    user = (f'Heard words: "{heard}"\nWhere it was said: "{window}"\nFindings: {", ".join(findings) or "none"}\n'
            f'Other medicines: {", ".join(others) or "none"}\nCandidates:\n' + '\n'.join(lines))
    ranking, model = None, None
    try:
        ranking, meta = client.generate(SYSTEM, user, Ranking, PROMPT_VERSION)
        model = f'{meta.provider}:{meta.model}'
    except Exception as error:
        log.warning('ranking failed, keeping the sound-alike order: %s', error)
    model_order, reasons = merge_ranking([c.entry.id for c, _ in picked], ranking)
    rank_of = {pid: i for i, pid in enumerate(model_order) if pid in reasons}
    fits = sorted(f['fit'] for f in facts.values() if f['fit'] is not None)
    middle = fits[len(fits) // 2] if fits else 0

    def blended(candidate):
        # The code decides the order; the model's rank is one input among sound, listing or popularity,
        # history and fit.
        pid = candidate.entry.id
        fit = facts[pid]['fit']
        return (candidate.score + standing(candidate.entry)
                + (PRIOR_BONUS if pid in priors else 0)
                + (MODEL_BONUS[rank_of[pid]] if rank_of.get(pid, 9) < len(MODEL_BONUS) else 0)
                + (FIT_WEIGHT * (fit - middle) if fit is not None else 0)
                - (MISMATCH_PENALTY if candidate.strength_match is False else 0))

    ranked = sorted(picked, key=lambda cp: blended(cp[0]), reverse=True)
    # The matcher's own formulary candidates (Pan 40 and Pan-D for a bare "Pan") always lead, in its order.
    ranked = ([cp for pid in rx.candidate_ids for cp in ranked if cp[0].entry.id == pid]
              + [cp for cp in ranked if cp[0].entry.id not in rx.candidate_ids])[:MAX_SUGGESTIONS]
    first_words = [c.entry.stem.split()[0] for c, _ in ranked]
    suggestions = []
    for index, (candidate, product) in enumerate(ranked):
        pid = candidate.entry.id
        suggestions.append({'product_id': pid, 'label': product_label(product), 'composition': composition_text(product),
                            'tier': 'formulary' if pid in formulary else candidate.entry.tier,
                            'sound': candidate.score, 'strength_match': candidate.strength_match,
                            'fit': facts[pid]['fit'], 'class': facts[pid]['class'], 'category': facts[pid]['category'],
                            'reason': reasons.get(pid), 'ranked_by_model': pid in reasons,
                            'chosen_before': priors.get(pid, 0),
                            # Another suggestion shares its brand's first word: Pan 40 beside Pan-D.
                            'sound_alike_sibling': first_words.count(first_words[index]) > 1,
                            'likely': False})
    mark_likely(suggestions, model_used=model is not None)
    return suggestions, {'candidates': len(picked), 'ranker': model, 'prompt_version': PROMPT_VERSION}


def mark_likely(suggestions, model_used):
    """The first suggestion is "likely" only with a clear lead: it sounds close, no other sounds almost as
    close, no sound-alike sibling is listed, its strength doesn't disagree, and the model ranked it first
    or the doctor chose it before. Anything less stays "possible matches" for the doctor to pick."""
    if not suggestions:
        return suggestions
    top = suggestions[0]
    top['likely'] = (top['sound'] >= CONFIDENT_SOUND and not top['sound_alike_sibling']
                     and top['strength_match'] is not False
                     and all(s['sound'] < top['sound'] - CONFIDENT_MARGIN for s in suggestions[1:])
                     and (top['ranked_by_model'] or not model_used or top['chosen_before'] > 0))
    return suggestions
