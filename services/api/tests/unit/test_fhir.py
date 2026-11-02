import json

import pytest

from conftest import REPO_ROOT
from voicerx.exports.fhir import build_bundles

EXAMPLE = REPO_ROOT.parent / "DATA/fhir/abdm_ig/Bundle-OPConsultNote-example-05.json"


def resources(bundle, kind):
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == kind]


def test_draft_cannot_be_exported(draft_report):
    with pytest.raises(ValueError):
        build_bundles(draft_report)


def test_document_bundle_starts_with_composition_and_every_reference_resolves(approved_report):
    bundle = build_bundles(approved_report)["op_consult"]
    assert bundle["type"] == "document"
    assert bundle["entry"][0]["resource"]["resourceType"] == "Composition"
    full_urls = {e["fullUrl"] for e in bundle["entry"]}
    references = {m for m in json.dumps(bundle).split('"reference": "')[1:]}
    assert all(r.split('"')[0] in full_urls for r in references)


def test_absent_finding_is_never_a_positive_resource(approved_report):
    bundle = build_bundles(approved_report)["op_consult"]
    assert not any("fever" in json.dumps(r).lower() for r in resources(bundle, "Condition") + resources(bundle, "Observation"))


@pytest.mark.skipif(not EXAMPLE.exists(), reason="ABDM examples not downloaded")
def test_profile_and_composition_type_match_the_official_example(approved_report):
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    bundle = build_bundles(approved_report)["op_consult"]
    assert bundle["meta"]["profile"] == example["meta"]["profile"]
    assert bundle["entry"][0]["resource"]["type"] == example["entry"][0]["resource"]["type"]


def test_as_needed_medicine_has_no_invented_timing(approved_report):
    request = resources(build_bundles(approved_report)["prescription"], "MedicationRequest")[0]
    assert request["dosageInstruction"][0]["asNeededBoolean"] is True
    assert "timing" not in request["dosageInstruction"][0]


def test_medicine_text_is_the_frozen_label(approved_report):
    request = resources(build_bundles(approved_report)["prescription"], "MedicationRequest")[0]
    assert request["medicationCodeableConcept"]["text"] == approved_report.medicines[0].label
