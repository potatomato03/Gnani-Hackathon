"""Build the starter formulary from the downloaded medicine list.

Every row starts as verified=false. A person checks it against a named source
and records who checked it and when.

    python -I tools/corpus/build_formulary.py
"""

import csv
import json
import os
import re
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT = re.compile(r"^(.*?)\s*\(([\d.]+)\s*([a-zA-Z%]+)\)\s*$")
SOURCE_ID = "indian-medicine-dataset@7c06a88"
FIELDS = [
    "id", "brand", "manufacturer", "form", "release_type", "components", "aliases",
    "specialty_tags", "source_id", "dataset_name", "verified", "checked_by", "checked_on",
]
GENERAL = "general_medicine"
ORTHO = "orthopaedics"
# id, name in the dataset, brand, form, release type, aliases, specialty tags
PRODUCTS = [
    ("p-dolo-650", "Dolo 650 Tablet", "Dolo 650", "tablet", "not_stated", "Dolo", GENERAL),
    ("p-azithral-500", "Azithral 500 Tablet", "Azithral 500", "tablet", "not_stated", "Azithral", GENERAL),
    ("p-augmentin-625", "Augmentin 625 Duo Tablet", "Augmentin 625 Duo", "tablet", "not_stated", "Augmentin", GENERAL),
    ("p-pan-40", "Pan 40 Tablet", "Pan 40", "tablet", "not_stated", "Pan", GENERAL),
    ("p-pan-d", "Pan-D Capsule PR", "Pan-D", "capsule", "prolonged", "Pan;Pan D", GENERAL),
    ("p-pantop-40", "Pantop 40 Tablet", "Pantop 40", "tablet", "not_stated", "Pantop", GENERAL),
    ("p-telma-40", "Telma 40 Tablet", "Telma 40", "tablet", "not_stated", "Telma", GENERAL),
    ("p-telma-h", "Telma H Tablet", "Telma H", "tablet", "not_stated", "", GENERAL),
    ("p-amlong-5", "Amlong Tablet", "Amlong", "tablet", "not_stated", "", GENERAL),
    ("p-amlong-2-5", "Amlong 2.5 Tablet", "Amlong 2.5", "tablet", "not_stated", "", GENERAL),
    ("p-glycomet-500-sr", "Glycomet 500 SR Tablet", "Glycomet 500 SR", "tablet", "sustained", "Glycomet", GENERAL),
    ("p-atorva-10", "Atorva Tablet", "Atorva", "tablet", "not_stated", "", GENERAL),
    ("p-atorva-20", "Atorva 20 Tablet", "Atorva 20", "tablet", "not_stated", "", GENERAL),
    ("p-thyronorm-50", "Thyronorm 50mcg Tablet", "Thyronorm 50mcg", "tablet", "not_stated", "Thyronorm", GENERAL),
    ("p-okacet", "Okacet Tablet", "Okacet", "tablet", "not_stated", "", GENERAL),
    ("p-montair-lc", "Montair-LC Tablet", "Montair-LC", "tablet", "not_stated", "Montair LC", GENERAL),
    ("p-combiflam", "Combiflam Tablet", "Combiflam", "tablet", "not_stated", "", f"{GENERAL};{ORTHO}"),
    ("p-voveran-50", "Voveran 50 GE Tablet", "Voveran 50 GE", "tablet", "not_stated", "Voveran", ORTHO),
    ("p-ondem-4", "Ondem 4 Tablet", "Ondem 4", "tablet", "not_stated", "Ondem", GENERAL),
    ("p-wysolone-10", "Wysolone 10 Tablet DT", "Wysolone 10", "tablet", "dispersible", "Wysolone", GENERAL),
    ("p-asthalin-100", "Asthalin 100mcg Inhaler", "Asthalin 100mcg", "inhaler", "not_stated", "Asthalin", GENERAL),
    ("p-ecosprin-75", "Ecosprin 75 Tablet", "Ecosprin 75", "tablet", "not_stated", "Ecosprin", GENERAL),
    ("p-taxim-o-200", "Taxim-O 200 Tablet", "Taxim-O 200", "tablet", "not_stated", "Taxim-O", GENERAL),
    ("p-novamox-500", "Novamox 500 Capsule", "Novamox 500", "capsule", "not_stated", "Novamox", GENERAL),
    ("p-rabicip-20", "Rabicip 20 Tablet", "Rabicip 20", "tablet", "not_stated", "Rabicip", GENERAL),
]


def parse_components(*parts):
    components = []
    for part in parts:
        if not isinstance(part, str) or not part.strip():
            continue
        match = COMPONENT.match(part)
        if match is None:
            raise ValueError(f"no strength in composition: {part!r}")
        components.append({"ingredient": match[1].strip(), "strength": match[2], "unit": match[3]})
    return components


def find_product(dataset, name):
    available = dataset[dataset["Is_discontinued"] == False]  # noqa: E712
    matches = available[available["name"].str.lower() == name.lower()]
    if matches.empty:
        raise ValueError(f"{name} is not in the dataset")
    return matches.iloc[0]


def build_rows(dataset):
    rows = []
    for product_id, name, brand, form, release, aliases, tags in PRODUCTS:
        record = find_product(dataset, name)
        components = parse_components(record["short_composition1"], record["short_composition2"])
        rows.append(
            {
                "id": product_id,
                "brand": brand,
                "manufacturer": record["manufacturer_name"],
                "form": form,
                "release_type": release,
                "components": json.dumps(components, ensure_ascii=False),
                "aliases": aliases,
                "specialty_tags": tags,
                "source_id": SOURCE_ID,
                "dataset_name": record["name"],
                "verified": "false",
                "checked_by": "",
                "checked_on": "",
            }
        )
    return rows


def main():
    data_dir = Path(os.environ.get("DATA_DIR", REPO_ROOT.parent / "DATA"))
    source = data_dir / "formulary" / "indian_medicine_dataset" / "indian_medicine_data.csv"
    dataset = pd.read_csv(source, low_memory=False, encoding_errors="replace")
    rows = build_rows(dataset)
    target = REPO_ROOT / "data" / "formulary" / "products.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {target.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
