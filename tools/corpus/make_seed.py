"""Write the fictional clinic, doctors and patients to data/seed/.

The output is repeatable. Phone numbers use a range no Indian mobile can have.

    python tools/corpus/make_seed.py
"""

import json
from pathlib import Path

from faker import Faker

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = 2704
LANGUAGES = ["hi-IN", "hi-IN", "en-IN", "te-IN", "ta-IN"]
CONSENTS = ["recording", "ai_processing", "call"]
# Details the case families depend on.
CASE_PATIENTS = {
    "pat-001": {"sex": "F", "birth_year": 1994, "language_pref": "hi-IN", "allergy_status": "nka"},
    "pat-002": {"sex": "M", "birth_year": 1979, "language_pref": "hi-IN", "allergy_status": "nka"},
    "pat-003": {"sex": "F", "birth_year": 1988, "language_pref": "en-IN", "allergy_status": "nka"},
    "pat-004": {"sex": "M", "birth_year": 1968, "language_pref": "en-IN", "allergy_status": "nka"},
    "pat-005": {"sex": "M", "birth_year": 1971, "language_pref": "hi-IN", "allergy_status": "nka"},
    "pat-006": {"sex": "F", "birth_year": 1983, "language_pref": "ta-IN", "allergy_status": "unknown"},
    "pat-007": {"sex": "M", "birth_year": 1999, "language_pref": "hi-IN", "allergy_status": "nka"},
    "pat-008": {"sex": "F", "birth_year": 1975, "language_pref": "hi-IN", "allergy_status": "nka"},
    "pat-009": {"sex": "M", "birth_year": 1981, "language_pref": "hi-IN", "allergy_status": "nka"},
    "pat-010": {"sex": "F", "birth_year": 1990, "language_pref": "hi-IN", "allergy_status": "nka"},
    "pat-011": {"sex": "M", "birth_year": 1962, "language_pref": "hi-IN", "allergy_status": "nka"},
    "pat-012": {
        "sex": "F",
        "birth_year": 1996,
        "language_pref": "te-IN",
        "allergy_status": "known",
        "allergies": ["penicillin"],
    },
}


def build_patients(count):
    fake = Faker("en_IN")
    fake.seed_instance(SEED)
    patients = []
    for number in range(1, count + 1):
        patient_id = f"pat-{number:03d}"
        details = CASE_PATIENTS.get(patient_id, {})
        sex = details.get("sex", fake.random_element(["F", "M"]))
        first_name = fake.first_name_female() if sex == "F" else fake.first_name_male()
        patients.append(
            {
                "patient_id": patient_id,
                "synthetic": True,
                "mrn": f"DEMO-MRN-{number:04d}",
                "name": f"{first_name} {fake.last_name()}",
                "sex": sex,
                "birth_year": details.get("birth_year", fake.random_int(1955, 2005)),
                "phone": f"+91-00000-{number:05d}",
                "language_pref": details.get("language_pref", fake.random_element(LANGUAGES)),
                "allergy_status": details.get("allergy_status", "unknown"),
                "allergies": details.get("allergies", []),
                "consents": CONSENTS,
            }
        )
    return patients


def build_doctors():
    fake = Faker("en_IN")
    fake.seed_instance(SEED + 1)
    specialties = ["general_medicine", "orthopaedics", "general_medicine"]
    return [
        {
            "doctor_id": f"doc-{number:03d}",
            "synthetic": True,
            "clinic_id": "clinic-001",
            "name": f"Dr {fake.first_name()} {fake.last_name()}",
            "role": "doctor",
            "specialty": specialty,
            "nmc_reg_no": f"DEMO-REG-{number:04d}",
        }
        for number, specialty in enumerate(specialties, start=1)
    ]


def build_clinic():
    return {
        "clinic_id": "clinic-001",
        "synthetic": True,
        "name": "Demo Clinic (Synthetic)",
        "phone": "+91-00000-90000",
    }


def main():
    seed_dir = REPO_ROOT / "data" / "seed"
    outputs = {
        "clinic.json": build_clinic(),
        "doctors.json": build_doctors(),
        "patients.json": build_patients(30),
    }
    for name, content in outputs.items():
        text = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
        (seed_dir / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {', '.join(outputs)} to data/seed/")


if __name__ == "__main__":
    main()
