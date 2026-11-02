"""Offline gold-data evaluation. Never imported by the extraction pipeline."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import unicodedata

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / 'tools/corpus'))
sys.path.insert(0, str(REPO_ROOT / 'services/api'))
import yaml
from rapidfuzz.fuzz import token_set_ratio
from case_schema import Family
from check_cases import effective
from voicerx.contracts.report import DraftReport
from voicerx.pipeline.run import SOURCES


def tokens(text):
    text = unicodedata.normalize('NFC', text).casefold()
    return set(''.join(c if unicodedata.category(c)[0] in 'LMN' else ' ' for c in text).split())


def match_items(expected, kept, typed):
    candidates = []
    for ei, (eid, evidence) in enumerate(expected):
        for ki, (kid, quote) in enumerate(kept):
            wanted = tokens(evidence)
            score = len(wanted & tokens(quote)) / len(wanted) if typed and wanted else (
                token_set_ratio(evidence, quote) / 100 if not typed else 0)
            if score >= (0.6 if typed else 0.7):
                candidates.append((-score, ei, ki, eid, kid))
    used_expected, used_kept, pairs = set(), set(), []
    for _, _, _, eid, kid in sorted(candidates):
        if eid not in used_expected and kid not in used_kept:
            used_expected.add(eid)
            used_kept.add(kid)
            pairs.append((eid, kid))
    return pairs


def extracted_name(rx, typed):
    """Pairing text for an extracted medicine. A quote of only the brand ("Wysolone") must still pair with
    evidence that includes the strength ("Wysolone ten"), so typed pairing uses the quote and spoken name."""
    return rx.quotes.get('name_quote', '') + ' ' + rx.spoken_name if typed else rx.spoken_name


def metric(count, total):
    return {'count': count, 'total': total}


def score_variant(encounter, variant, draft, source):
    facts, medicines, unknown = effective(encounter, variant)
    if unknown:
        raise ValueError('Unknown expected ids: ' + ', '.join(unknown))
    facts = [f for f in facts if f.delivery == 'spoken']
    kept = draft.checked.kept
    typed = source == 'typed'
    pairs = match_items([(f.id, variant.evidence.get(f.id, '') if typed else f.text) for f in facts],
                        [(x.id, x.quote if typed else x.term) for x in kept], typed)
    gold, actual = {f.id: f for f in facts}, {x.id: x for x in kept}
    medicine_pairs = match_items(
        [(m.id, variant.evidence.get(m.id + '.name', '') if typed else m.spoken_name) for m in medicines],
        [(m.id, extracted_name(m, typed)) for m in draft.checked.medications], typed)
    gold_rx = {m.id: m for m in medicines}
    actual_rx = {m.id: m for m in draft.checked.medications}
    fields = ('product_id', 'dose', 'schedule', 'food', 'duration')
    def value(obj, field):
        val = getattr(obj, field)
        return val.model_dump(mode='json') if hasattr(val, 'model_dump') else val
    exact = sum(all(value(gold_rx[g], f) == value(actual_rx[a], f) for f in fields) for g, a in medicine_pairs)
    expected_flags = set(variant.expected_flags)
    flags = {i.code for i in draft.issues}
    unexpected = [i.model_dump() for i in draft.issues if i.severity == 'block' and i.code not in expected_flags]
    lines = [(section, line) for section, rows in draft.sections.items() for line in rows]
    cited = Counter(c for _, line in lines for c in set(line.cites))
    section_right = sum(any(gold[g].section == section and a in line.cites for section, line in lines) for g, a in pairs)
    result = {
        'approximate': not typed,
        'facts_found': metric(len(pairs), len(facts)),
        'facts_missed': metric(len(facts) - len(pairs), len(facts)),
        'false_facts': metric(len(kept) - len(pairs), len(kept)),
        'negation_accuracy': metric(sum(gold[g].assertion == actual[a].assertion for g, a in pairs), len(pairs)),
        'side_accuracy': metric(sum(gold[g].laterality == actual[a].laterality for g, a in pairs), len(pairs)),
        'medicines_exact': metric(exact, len(medicines)),
        'extra_medicines': metric(len(actual_rx) - len(medicine_pairs), len(actual_rx)),
        'expected_flags': metric(len(expected_flags & flags), len(expected_flags)),
        'section_accuracy': metric(section_right, len(pairs)),
        'report_omissions': metric(sum(not cited[x.id] for x in kept), len(kept)),
        'report_duplications': metric(sum(cited[x.id] > 1 for x in kept), len(kept)),
        'unsupported_lines': metric(sum(not line.cites or any(c not in actual for c in line.cites) for _, line in lines), len(lines)),
        'unexpected_blocking_flags': unexpected,
        'missing_expected_flags': sorted(expected_flags - flags),
        'fact_matches': pairs,
        'medicine_matches': medicine_pairs,
        'unmatched_expected_facts': [f.id for f in facts if f.id not in {p[0] for p in pairs}],
        'unmatched_extracted_facts': [x.id for x in kept if x.id not in {p[1] for p in pairs}],
        'attribute_mismatches': [dict(expected=g, extracted=a, field=f,
            expected_value=getattr(gold[g], f), actual_value=getattr(actual[a], f))
            for g, a in pairs for f in ('assertion', 'laterality', 'subject', 'certainty', 'temporality')
            if getattr(gold[g], f) != getattr(actual[a], f)],
    }
    return result


def score_run(run_dir, source):
    if source not in SOURCES:
        raise ValueError('source must be one of ' + ', '.join(SOURCES))
    families = [Family.model_validate(yaml.safe_load(p.read_text(encoding='utf-8')))
                for p in sorted((REPO_ROOT / 'data/eval/cases').glob('*.yaml'))]
    gold = {v.variant_id: (e, v) for f in families for e in f.encounters for v in e.variants}
    result = dict(run_id=run_dir.name, source=source, approximate=source != 'typed', scored=0,
                  missing_input=[], incomplete=[], cases={}, metrics={}, unexpected_blocking_flags=0)
    for directory in sorted(run_dir.iterdir()):
        if not directory.is_dir() or directory.name not in gold:
            continue
        status_path = directory / 'status.json'
        status = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {'status': 'incomplete'}
        if status.get('status') != 'draft':
            key = 'missing_input' if status.get('status') == 'missing_input' else 'incomplete'
            result[key].append(directory.name)
            result['cases'][directory.name] = status
            continue
        # Score the original machine output even after a doctor has resolved it.
        path = directory / 'draft_report.v1.json'
        if not path.exists():
            path = directory / 'draft_report.json'
        draft = DraftReport.model_validate_json(path.read_text(encoding='utf-8'))
        scores = score_variant(*gold[directory.name], draft, source)
        meta_path = directory / 'meta.json'
        scores['model_metadata'] = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.exists() else {}
        result['cases'][directory.name] = scores
        result['scored'] += 1
        result['unexpected_blocking_flags'] += len(scores['unexpected_blocking_flags'])
        for name, val in scores.items():
            if isinstance(val, dict) and set(val) == {'count', 'total'}:
                aggregate = result['metrics'].setdefault(name, metric(0, 0))
                for field in ('count', 'total'):
                    aggregate[field] += val[field]
    result['not_run'] = sorted(set(gold) - set(result['cases']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--source', required=True, choices=SOURCES)
    args = parser.parse_args()
    scores = score_run(args.run_dir, args.source)
    out = REPO_ROOT / 'data/eval/results/scores' / (args.run_dir.name + '.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scores, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"{args.run_dir.name}: {scores['scored']} scored; {len(scores['missing_input'])} missing; {len(scores['incomplete'])} incomplete")
    for name, val in scores['metrics'].items():
        print(f"{name:26} {val['count']:4} / {val['total']}")
    print(f"Unexpected blocking flags: {scores['unexpected_blocking_flags']}")
    print(out)


if __name__ == '__main__':
    main()
