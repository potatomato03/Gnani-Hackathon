from datetime import date, datetime, time, timedelta

import pytest

from voicerx.agent.demo import build_visit
from voicerx.agent.plan import IST, plan_followups


@pytest.fixture(scope="module")
def visits(tmp_path_factory):
    out = tmp_path_factory.mktemp("visits")
    return {case: build_visit(case, out) for case in ("fam-001-a", "fam-004-a", "fam-010-a")}


def kinds(plan):
    return [(t.kind, t.due_at.astimezone(IST).date().isoformat(), t.questions) for t in plan.touches if t.status == "planned"]


def test_every_demo_visit_is_approved_with_no_blocking_issue(visits):
    for visit in visits.values():
        assert visit.approved.status == "approved"
        assert not [i for i in visit.approved.issues if i.severity == "block"]


def test_continued_medicine_is_cleared_only_by_an_audited_doctor_correction(visits):
    approved = visits["fam-004-a"].approved
    assert {r.action for r in approved.resolutions} == {"set_dose", "set_timing"}
    assert all(r.by and r.reason for r in approved.resolutions)
    assert approved.version == 2


def test_short_as_needed_course_gets_one_merged_check_on_its_last_day(visits):
    plan = plan_followups(visits["fam-001-a"])
    # Dolo for 3 days from 5 Oct: the day-2 tolerance check and the end of course fall on 7 Oct and merge.
    # Every medicine is as-needed, so there is no adherence question.
    assert kinds(plan) == [
        ("summary", "2026-10-05", []),
        ("end_of_course", "2026-10-07", ["tolerance", "symptom_status"]),
    ]


def test_taper_inhaler_and_long_course_with_a_confirmed_review(visits):
    plan = plan_followups(visits["fam-010-a"])
    assert kinds(plan) == [
        ("summary", "2026-10-19", []),
        ("tolerance", "2026-10-21", ["tolerance"]),
        # The taper ends on 24 Oct, two days before the confirmed review: one merged touch, named for the review.
        ("review", "2026-10-24", ["symptom_status", "adherence", "review_attendance"]),
        ("progress", "2026-11-03", ["symptom_status", "adherence"]),
        ("end_of_course", "2026-11-17", ["symptom_status", "adherence"]),
    ]


def test_no_review_touch_without_a_doctor_confirmed_date(visits):
    visit = visits["fam-010-a"]
    unconfirmed = visit.model_copy(update={"review_date": None})
    assert "review_attendance" not in [q for t in plan_followups(unconfirmed).touches for q in t.questions]


def test_continued_chronic_medicine_without_a_course_gets_no_scheduled_check(visits):
    assert kinds(plan_followups(visits["fam-004-a"])) == [("summary", "2026-10-09", [])]


def test_scheduled_touches_fall_inside_quiet_hours_and_never_exceed_five(visits):
    for visit in visits.values():
        plan = plan_followups(visit)
        planned = [t for t in plan.touches if t.status == "planned"]
        assert len(planned) <= 5
        days = [t.due_at.astimezone(IST).date() for t in planned]
        assert len(days) == len(set(days))
        for touch in planned:
            local = touch.due_at.astimezone(IST).time()
            assert time(9) <= local <= time(20)


def test_late_approval_moves_the_summary_to_the_next_morning(visits):
    visit = visits["fam-001-a"]
    late = visit.model_copy(update={"approved": visit.approved.model_copy(
        update={"approved_at": datetime.combine(date(2026, 10, 5), time(22, 30), IST)})})
    summary = plan_followups(late).touches[0]
    assert summary.due_at.astimezone(IST) == datetime.combine(date(2026, 10, 6), time(9), IST)


def test_plan_is_tied_to_the_approved_fingerprint(visits):
    visit = visits["fam-010-a"]
    plan = plan_followups(visit)
    assert plan.report_hash == visit.approved.content_hash
    assert plan.patient_id == "pat-010" and plan.language == "hi-IN"
    assert plan.touches[0].due_at - visit.approved.approved_at < timedelta(minutes=1)
