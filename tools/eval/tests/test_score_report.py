import json

from score_report import extracted_name, match_items, score_run


def test_typed_quotes_match_by_overlap():
    pairs = match_items(expected=[("f1", "बुखार नहीं है")], kept=[("x1", "बुखार नहीं है")], typed=True)
    assert pairs == [("f1", "x1")]


def test_weak_overlap_does_not_match():
    assert match_items(expected=[("f1", "तीन दिन से गले में दर्द")], kept=[("x1", "तीन दिन तक")], typed=True) == []


def test_one_extracted_item_cannot_match_two_facts():
    pairs = match_items(expected=[("f1", "No fever"), ("f2", "No fever")], kept=[("x1", "No fever")], typed=True)
    assert len(pairs) == 1


def test_missing_and_incomplete_cases_are_listed_not_dropped(tmp_path):
    for case, status in [("fam-001-a", "missing_input"), ("fam-001-b", "incomplete")]:
        (tmp_path / case).mkdir()
        (tmp_path / case / "status.json").write_text(json.dumps({"status": status}), encoding="utf-8")
    scores = score_run(tmp_path, "typed")
    assert (scores["missing_input"], scores["incomplete"], scores["scored"]) == (["fam-001-a"], ["fam-001-b"], 0)


def fixture_score(changed_dose=False):
    import yaml
    from score_report import REPO_ROOT, Family, score_variant
    from voicerx.contracts.extraction import Extraction
    from voicerx.contracts.report import ReportFields
    from voicerx.pipeline.check_extraction import check_extraction
    from voicerx.pipeline.assemble import assemble_draft
    from voicerx.reference import load_reference
    family = Family.model_validate(yaml.safe_load((REPO_ROOT / 'data/eval/cases/fam-001.yaml').read_text(encoding='utf-8')))
    encounter = family.encounters[0]
    variant = encounter.variants[0]
    directory = REPO_ROOT / 'services/api/tests/fixtures/fam-001-a'
    extraction = Extraction.model_validate_json((directory / 'extraction.json').read_text(encoding='utf-8'))
    fields = ReportFields.model_validate_json((directory / 'report_fields.json').read_text(encoding='utf-8'))
    reference = load_reference(REPO_ROOT)
    checked = check_extraction(extraction, '\n'.join(u.text for u in variant.utterances), reference,
                               family.patient_id, encounter.date)
    if changed_dose:
        checked.medications[0].dose.amount = '2'
    draft = assemble_draft(variant.variant_id, family.patient_id, encounter.doctor_id, encounter.date,
                           fields, checked, [], reference)
    return score_variant(encounter, variant, draft, 'typed')


def test_clean_fixture_scores_all_facts_and_medicine():
    scores = fixture_score()
    assert scores['facts_found'] == {'count': 8, 'total': 8}
    assert scores['false_facts'] == {'count': 0, 'total': 8}
    assert scores['medicines_exact'] == {'count': 1, 'total': 1}
    assert scores['section_accuracy'] == {'count': 8, 'total': 8}


def test_wrong_dose_never_gets_exact_medicine_credit():
    assert fixture_score(changed_dose=True)['medicines_exact'] == {'count': 0, 'total': 1}


def test_medicine_pairs_on_its_spoken_name_when_the_quote_is_only_the_brand():
    # typed-groq-2: quote "Wysolone" against evidence "Wysolone ten" left fam-010-a unpaired (runbook C-53).
    from voicerx.contracts.extraction import ResolvedMedication
    from voicerx.contracts.medication import Start
    rx = ResolvedMedication(id="rx1", action="start", spoken_name="Wysolone ten", match="exact",
                            product_id="p-wysolone-10", candidate_ids=["p-wysolone-10"], dose=None, schedule=None,
                            food=None, duration=None, start=Start(), route=None, unresolved=[],
                            quotes={"name_quote": "Wysolone"})
    assert match_items([("m1", "Wysolone ten")], [("rx1", extracted_name(rx, typed=True))], typed=True) == [("m1", "rx1")]
