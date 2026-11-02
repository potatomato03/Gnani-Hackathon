"""Read only the catalog and seed records, never evaluation answers."""
import csv
import json
from pathlib import Path
import yaml
from .contracts.medication import Strict


class Component(Strict):
    ingredient: str
    strength: str
    unit: str


class Product(Strict):
    id: str
    brand: str
    manufacturer: str
    form: str
    release_type: str
    components: list[Component]
    aliases: list[str]


class Reference(Strict):
    products: dict[str, Product]
    patients: dict[str, dict]
    doctors: dict[str, dict]
    clinic: dict
    allergy_classes: dict[str, list[str]]
    allergy_classes_reviewed: bool


def load_reference(repo_root: Path) -> Reference:
    data = repo_root / "data"
    with (data / "formulary/products.csv").open(encoding="utf-8", newline="") as handle:
        products = {}
        for row in csv.DictReader(handle):
            fields = {k: row[k] for k in ("id", "brand", "manufacturer", "form", "release_type")}
            products[row["id"]] = Product(**fields, components=json.loads(row["components"]),
                                         aliases=[a for a in row["aliases"].split(";") if a])
    def read(name):
        return json.loads((data / "seed" / name).read_text(encoding="utf-8"))
    rules = yaml.safe_load((data / "rules/allergy_classes.yaml").read_text(encoding="utf-8"))
    return Reference(products=products, patients={p["patient_id"]: p for p in read("patients.json")},
                     doctors={d["doctor_id"]: d for d in read("doctors.json")}, clinic=read("clinic.json"),
                     allergy_classes=rules["classes"], allergy_classes_reviewed=rules["reviewed"])
