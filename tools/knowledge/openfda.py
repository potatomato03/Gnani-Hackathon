"""Pick one openFDA label per ingredient set and route, for medicines sold in India, and chunk it by section.

US labels state US-approved uses and doses. Each chunk says which label it came from,
so an answer built on it can be traced and dated.
"""
from chunking import split_text
from names import ingredient_key

# Label field -> heading in the chunk. Clinical studies, pharmacology and packaging are left out.
SECTIONS = {
    'boxed_warning': 'Boxed warning', 'indications_and_usage': 'Uses', 'purpose': 'Purpose',
    'dosage_and_administration': 'Dosage', 'contraindications': 'Contraindications', 'do_not_use': 'Do not use',
    'warnings_and_cautions': 'Warnings and precautions', 'warnings': 'Warnings', 'precautions': 'Precautions',
    'ask_doctor': 'Ask a doctor', 'stop_use': 'Stop use', 'drug_interactions': 'Interactions',
    'use_in_specific_populations': 'Special populations', 'pregnancy': 'Pregnancy',
    'pregnancy_or_breast_feeding': 'Pregnancy or breastfeeding', 'nursing_mothers': 'Breastfeeding',
    'pediatric_use': 'Children', 'geriatric_use': 'Older adults', 'adverse_reactions': 'Side effects',
    'overdosage': 'Overdose',
}
KINDS = {'HUMAN PRESCRIPTION DRUG': 2, 'HUMAN OTC DRUG': 1}


def _ingredients(record):
    names = record.get('openfda', {}).get('substance_name') or []
    return frozenset(ingredient_key(n) for n in names)


def _rank(record):
    kind = max((KINDS.get(k, 0) for k in record['openfda'].get('product_type', [])), default=0)
    return kind, sum(field in record for field in SECTIONS), record.get('effective_time', '')


def select_labels(records, india_keys):
    """The best label for each (ingredients, route) whose every ingredient is sold in India."""
    best = {}
    for record in records:
        ingredients = _ingredients(record)
        if not ingredients or not ingredients <= india_keys:
            continue
        key = (ingredients, '+'.join(sorted(record['openfda'].get('route', []))))
        compact = {k: record[k] for k in ('set_id', 'effective_time', 'openfda', *SECTIONS) if k in record}
        if key not in best or _rank(compact) > _rank(best[key]):
            best[key] = compact
    return best


def label_chunks(record):
    openfda = record['openfda']
    # Substance names, not the label's generic_name, which can hold a brand or a typo.
    name = ' and '.join(sorted(openfda['substance_name'])).capitalize()
    routes = ', '.join(r.lower() for r in openfda.get('route', []))
    classes = ', '.join(c.removesuffix(' [EPC]') for c in openfda.get('pharm_class_epc', []))
    context = '; '.join(x for x in (routes, classes) if x)
    heading = f'{name} ({context})' if context else name
    url = 'https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=' + record['set_id']
    chunks = []
    for field, title in SECTIONS.items():
        parts = split_text(' '.join(record.get(field, [])))
        for index, part in enumerate(parts, 1):
            chunks.append({
                'id': f"{record['set_id']}:{field}:{index}", 'source': 'openfda_label', 'title': name,
                'section': title, 'part': index, 'parts': len(parts), 'ingredients': sorted(_ingredients(record)),
                'route': routes, 'classes': classes, 'text': f'{heading}. {title}: {part}', 'url': url,
                'date': record.get('effective_time', ''), 'licence': 'CC0 1.0 (openFDA)',
                'note': 'US label: uses and doses approved in the US, which may differ in India.'})
    return chunks
