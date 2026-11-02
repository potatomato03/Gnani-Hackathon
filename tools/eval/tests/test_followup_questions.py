from followup_questions import score


def test_every_demo_question_gets_its_expected_action_and_no_forbidden_claim():
    rows = score()
    assert len(rows) == 7
    assert [r for r in rows if not r[4] or r[5]] == []
