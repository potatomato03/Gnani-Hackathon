"""Jan Aushadhi's product list: one chunk per therapeutic group, listing its generics.

PMBI asks for permission before the list is reproduced in public, so these chunks
stay in the data folder outside the repo.
"""
import re

from names import ingredient_key

URL = 'https://janaushadhi.gov.in/ProductList.aspx'
PART_CHARS = 800
FORMS = re.compile(r'\b(?:tablets?|capsules?|injections?|ip|bp|usp|dispersible|chewable|syrup|suspension|solution|'
                   r'drops?|cream|gel|ointment|lotion|oral|eye|ear|nasal|spray|inhaler|powder|sachets?|kit|combi|'
                   r'sr|er|xr|cr|mr|film|coated|enteric|prolonged|sustained|extended|release|for|with|per|ml|i\.?v\.?)\b.*$',
                   re.IGNORECASE)


def _ingredients(generic):
    """'Artemether 80mg and Lumefantrine 480mg Tablets' -> {'artemether', 'lumefantrine'}."""
    parts = re.split(r'\s+and\s+|\s*\+\s*|,\s*', generic, flags=re.IGNORECASE)
    names = set()
    for part in parts:
        part = FORMS.sub('', re.split(r'\d', part)[0]).strip(' -.')
        if part:
            names.add(ingredient_key(part))
    return names


NOT_MEDICINES = {'surgical & medical consumables', 'mosquito repellent'}


def jan_aushadhi_chunks(rows):
    groups, names = {}, {}
    for row in rows:
        group = row['Group Name'].strip()
        key = group.casefold()
        if key in NOT_MEDICINES:
            continue
        # The list spells some groups two ways ("Anti-Viral", "Anti-viral"); the first spelling names both.
        names.setdefault(key, group)
        groups.setdefault(names[key], []).append(row['Generic Name'].strip())
    chunks = []
    for group in sorted(groups):
        # Every part repeats the group heading, and parts stay short, so a search for the
        # group's purpose finds each part, not just the first (a long bare list of names doesn't).
        heading = f'Jan Aushadhi (PMBJP) generic medicines in the group "{group}": '
        parts, current = [], []
        for generic in sorted(set(groups[group])):
            if current and len(heading) + len('; '.join(current + [generic])) + 1 > PART_CHARS:
                parts.append(current)
                current = []
            current.append(generic)
        parts.append(current)
        for number, listed in enumerate(parts, 1):
            chunks.append({'id': f'jan_aushadhi:{group}:{number}', 'source': 'jan_aushadhi', 'title': group,
                           'section': 'Therapeutic group', 'part': number, 'parts': len(parts),
                           'ingredients': sorted(set().union(*map(_ingredients, listed))),
                           'text': heading + '; '.join(listed) + '.', 'url': URL, 'date': '2026-11-02',
                           'licence': 'PMBI permission needed before public reuse'})
    return chunks
