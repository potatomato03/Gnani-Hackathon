"""Build the medicine knowledge chunks from the downloaded sources, outside the repo.

    python tools/knowledge/build_chunks.py

Reads ../DATA (or $DATA_DIR) and writes one JSON Lines file per source to
../DATA/knowledge/chunks/. The Indian Medicine Dataset is not chunked: it only
decides which generics are sold in India, and so which US labels are kept.
"""
import csv
import json
import os
import sys
import zipfile
from pathlib import Path

from chunking import write_jsonl
from jan_aushadhi import jan_aushadhi_chunks
from names import ingredients_of, product_composition
from nlem import nlem_chunks, parse_nlem
from openfda import label_chunks, select_labels

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get('DATA_DIR', REPO_ROOT.parent / 'DATA'))
OUT_DIR = DATA_DIR / 'knowledge' / 'chunks'
# NLEM's medicine tables run from PDF page 4 to page 84; the rest is front matter and annexures.
NLEM_PAGES = range(3, 84)


def india_ingredients():
    """Ingredient keys of every current allopathic product in the Indian Medicine Dataset."""
    path = DATA_DIR / 'formulary/indian_medicine_dataset/updated_indian_medicine_data.csv'
    keys = set()
    with path.open(encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['Is_discontinued'] != 'TRUE' and row['type'] == 'allopathy':
                keys |= ingredients_of(product_composition(row))
    return keys


def openfda_records():
    for path in sorted((DATA_DIR / 'knowledge/openfda_label').glob('drug-label-*.json.zip')):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                with archive.open(name) as handle:
                    yield from json.load(handle)['results']
        print(f'read {path.name}', flush=True)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    india = india_ingredients()
    print(f'{len(india)} ingredients sold in India', flush=True)
    labels = select_labels(openfda_records(), india)
    count = write_jsonl(OUT_DIR / 'openfda_label.jsonl', (c for r in labels.values() for c in label_chunks(r)))
    print(f'openFDA: {len(labels)} labels, {count} chunks', flush=True)

    from pypdf import PdfReader
    reader = PdfReader(str(DATA_DIR / 'formulary/nlem_2022/nlem2022.pdf'))
    medicines = parse_nlem([reader.pages[i].extract_text() for i in NLEM_PAGES])
    count = write_jsonl(OUT_DIR / 'nlem_2022.jsonl', nlem_chunks(medicines))
    print(f'NLEM 2022: {len(medicines)} medicines, {count} chunks', flush=True)

    jan = next((DATA_DIR / 'formulary/jan_aushadhi').glob('jan_aushadhi_product_list_*.csv'))
    with jan.open(encoding='utf-8-sig') as handle:
        count = write_jsonl(OUT_DIR / 'jan_aushadhi.jsonl', jan_aushadhi_chunks(csv.DictReader(handle)))
    print(f'Jan Aushadhi: {count} chunks', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
