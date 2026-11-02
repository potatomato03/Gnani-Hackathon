"""India's National List of Essential Medicines 2022: one chunk per medicine with its categories.

The PDF's text comes out as lines: "Section N" and its title, numbered sub-headings,
numbered medicines with their level of care (P, S, T) and dosage forms, and footnotes
saying where else a medicine is listed. The footnotes are skipped, because the other
listing appears in its own section anyway.
"""
import re

from chunking import split_text
from names import ingredient_key

URL = 'https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2018/UploadConsumer/nlem2022.pdf'
SECTION = re.compile(r'^Section\s+(\d+)\s*$')
NUMBERED = re.compile(r'^(?:Section\s+)?(\d+(?:\.\d+)+)(?![.\d])\s*-?\s*(.*)$')
LEVEL = re.compile(r'(?:^|\s)([PST](?:\s*,\s*[PST])*)(?=\s|$)')
TABLE_HEADER = 'Medicine Level of Healthcare'
NOTE = re.compile(r'\s+(?=a\)|All |In case )')


def _split_level(text):
    """('Allopurinol', 'P,S,T', 'Tablet 100 mg') from 'Allopurinol*** P,S,T Tablet 100 mg'."""
    match = LEVEL.search(text)
    if not match:
        return text, None, ''
    name = text[:match.start()].strip().rstrip('*').strip()
    return name, match[1].replace(' ', ''), text[match.end():].strip()


def _structural(line):
    return bool(NUMBERED.match(line) or SECTION.match(line) or TABLE_HEADER in line
                or line.startswith('*') or 'also listed' in line)


def parse_nlem(pages):
    medicines, headings, current, in_footnote = {}, {}, None, False
    spellings = {}
    lines = []
    for raw in (line for page in pages for line in page.splitlines()):
        line = ' '.join(raw.split())
        if TABLE_HEADER in line:
            # The table header can share a line with the heading above it.
            lines += [x for x in (line.split(TABLE_HEADER)[0].strip(), TABLE_HEADER) if x]
        elif line in ('Medicine', 'Level of') or 'Dosage form(s) and strength(s)' in line:
            # ... or be broken over three lines.
            lines.append(TABLE_HEADER)
        elif line:
            lines.append(line)
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        section = SECTION.match(line)
        if section and index < len(lines):
            headings = {section[1]: lines[index]}
            index += 1
            current, in_footnote = None, False
            continue
        if TABLE_HEADER in line:
            current, in_footnote = None, False
            continue
        if line.startswith('*') or 'also listed' in line:
            current, in_footnote = None, True
            continue
        numbered = NUMBERED.match(line)
        if numbered and not in_footnote:
            number, rest = numbered[1], numbered[2].strip()
            name, level, forms = _split_level(rest)
            if level is None:
                # The name or heading may wrap over the next lines, up to the line opening with the level.
                following = []
                while index + len(following) < len(lines) and len(following) < 6:
                    candidate = lines[index + len(following)]
                    if _structural(candidate):
                        break
                    following.append(candidate)
                    if LEVEL.match(candidate):
                        break
                if following and LEVEL.match(following[-1]):
                    name = ' '.join([rest, *following[:-1]]).replace('*', '').strip()
                    _, level, forms = _split_level(following[-1])
                    index += len(following)
                else:
                    headings = {k: v for k, v in headings.items() if not k.startswith(number + '.') and k != number}
                    # "Non-" at a line end joins its continuation: "Non-steroidal".
                    heading = re.sub(r'(\w-) (\w)', r'\1\2', ' '.join([rest, *following]))
                    # Some headings carry a long scope note ("All forms of ...", "a) All the vaccines ...").
                    headings[number] = NOTE.split(heading)[0].strip()
                    index += len(following)
                    current = None
                    continue
            parents = [headings[k] for k in sorted(headings, key=lambda k: k.count('.'))
                       if number.startswith(k + '.')]
            # Footnote marks and capitals differ between listings ("Doxycycline** #", "Sodium Valproate").
            name = ' '.join(re.sub(r'[*#]', ' ', name).split())
            name = spellings.setdefault(name.casefold(), name)
            entry = medicines.setdefault(name, {'categories': [], 'levels': [], 'forms': []})
            entry['categories'].append(' > '.join(parents))
            entry['levels'].append(level)
            entry['forms'].append(forms)
            current = entry
            continue
        if numbered and in_footnote:
            in_footnote = False
            index -= 1
            continue
        if current is not None and not in_footnote:
            current['forms'][-1] = (current['forms'][-1] + ' ' + line).strip()
    return medicines


def nlem_ingredients(name):
    """'Co-trimoxazole [Sulphamethoxazole (A) + Trimethoprim (B)]' -> ['sulfamethoxazole', 'trimethoprim']."""
    inner = re.search(r'\[(.+)\]', name)
    text = re.sub(r'\([^)]*\)', ' ', inner[1] if inner else name)
    return sorted({ingredient_key(p) for p in text.split('+') if p.strip()})


def nlem_chunks(medicines):
    chunks = []
    for name, entry in sorted(medicines.items()):
        listings = '; '.join(f'{category} (level {level}): {forms}'.rstrip(': ')
                             for category, level, forms in zip(entry['categories'], entry['levels'], entry['forms']))
        text = (f"{name} is on India's National List of Essential Medicines 2022. Listed under: {listings}. "
                'Levels of care: P = primary, S = secondary, T = tertiary.')
        parts = split_text(text)
        ingredients = nlem_ingredients(name)
        for number, part in enumerate(parts, 1):
            # The full name, not its ingredient key: "Betamethasone" and its dipropionate are listed apart.
            slug = re.sub(r'[^a-z0-9]+', '-', name.casefold()).strip('-')
            chunks.append({'id': f'nlem:{slug}:{number}', 'source': 'nlem_2022', 'title': name,
                           'section': 'Essential medicine listing', 'part': number, 'parts': len(parts),
                           'ingredients': ingredients, 'text': part, 'url': URL, 'date': '2022',
                           'licence': 'Government of India publication; no licence stated'})
    return chunks
