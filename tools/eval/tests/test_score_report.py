import json

from score_report import match_items, score_run


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
