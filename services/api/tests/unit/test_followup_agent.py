from datetime import datetime, time

import pytest

from voicerx.agent import conversation as conv_mod
from voicerx.agent.conversation import advance, receive, start
from voicerx.agent.demo import build_visit
from voicerx.agent.gate import GateRefused, check_reply
from voicerx.agent.ground import answer_medicine_question
from voicerx.agent.plan import IST
from voicerx.agent.redflags import find_red_flags
from voicerx.agent.templates import load_templates


@pytest.fixture(scope="module")
def visits(tmp_path_factory):
    out = tmp_path_factory.mktemp("visits")
    return {case: build_visit(case, out) for case in ("fam-001-a", "fam-004-a", "fam-010-a")}


def consented(visit):
    return visit


@pytest.fixture
def dolo(visits):
    return start(consented(visits["fam-001-a"]), "c-dolo")


@pytest.fixture
def asthma(visits):
    return start(consented(visits["fam-010-a"]), "c-asthma")


def last(conv, sender="clinic"):
    return [m for m in conv.messages if m.sender == sender][-1]


def task_kinds(conv):
    return [t.kind for t in conv.tasks]


# Red flags

@pytest.mark.parametrize("text, flag", [
    ("seene mein dard ho raha hai", "chest_pain"),
    ("सीने में दर्द हो रहा है", "chest_pain"),
    ("I have chest pain since morning", "chest_pain"),
    ("साँस बिल्कुल नहीं आ रही, बोल भी नहीं पा रही।", "severe_breathlessness"),
    ("सांस बिल्कुल नहीं आ रही", "severe_breathlessness"),       # anusvara for chandrabindu
    ("साँस ज्यादा फूल रही है", "severe_breathlessness"),          # no nukta
    ("my face is swelling after the tablet", "severe_allergy"),
    ("kal raat behosh ho gayi thi", "fainting"),
])
def test_red_flags_fire_in_every_spelling(text, flag):
    assert flag in find_red_flags(text)


@pytest.mark.parametrize("text", [
    "no chest pain, just cough",
    "I don't have chest pain",
    "सीने में दर्द नहीं है",
    "seene mein dard nahi hai",
    "throat pain is better",
    "Wysolone अभी बंद कर दूँ?",
])
def test_negated_or_unrelated_text_does_not_fire(text):
    assert find_red_flags(text) == []


# The first message

def test_summary_discloses_ai_and_gives_the_fixed_medicine_rows(dolo, visits):
    summary = dolo.messages[0]
    t = load_templates("hi-IN")
    assert summary.kind == "summary" and summary.sender == "clinic"
    assert "AI" in summary.text and "DOCTOR" in summary.text and "STOP" in summary.text
    assert "DOLO 650" in summary.text and "खाने के बाद" in summary.text   # from the fixed Hindi template
    assert summary.text.index("AI") < summary.text.index("DOLO")
    assert summary.cites == ["rx1"]
    assert dolo.plan.report_hash == visits["fam-001-a"].approved.content_hash
    assert t["keywords_help"] in summary.text


def test_english_patient_gets_the_corrected_approved_row(visits):
    conv = start(consented(visits["fam-004-a"]), "c-telma")
    assert "TELMA 40" in conv.messages[0].text and "1 tablet" in conv.messages[0].text
    assert "Your doctor prescribed" in conv.messages[0].text


def test_seed_patients_carry_follow_up_consent(visits):
    assert all("followup_whatsapp" in v.consents for v in visits.values())


def test_no_consent_means_no_message(visits):
    withdrawn = visits["fam-001-a"].model_copy(update={"consents": ["recording", "ai_processing", "call"]})
    with pytest.raises(GateRefused, match="consent"):
        start(withdrawn, "c-none")


# Check-ins

def test_advance_sends_the_next_check_in_with_buttons(dolo):
    advance(dolo)
    question = last(dolo)
    assert question.kind == "question" and [b.id for b in question.buttons] == ["no_problem", "some_problem", "stopped"]
    assert dolo.clock.astimezone(IST).date().isoformat() == "2026-10-07"
    assert time(9) <= dolo.clock.astimezone(IST).time() <= time(20)


def test_button_answers_walk_the_merged_touch_and_record_each_answer(dolo):
    advance(dolo)
    receive(dolo, button="no_problem")
    assert [b.id for b in last(dolo).buttons] == ["better", "same", "worse"]
    receive(dolo, button="better")
    answers = [a for r in dolo.records for a in r.answers]
    assert [(a.question, a.value) for a in answers] == [("tolerance", "no_problem"), ("symptom_status", "better")]
    assert dolo.awaiting is None and dolo.tasks == []
    assert all(r.synthetic and r.report_hash == dolo.report_hash for r in dolo.records)


def test_worse_creates_a_doctor_task_and_gives_safety_advice(dolo):
    advance(dolo)
    receive(dolo, button="no_problem")
    receive(dolo, button="worse")
    assert task_kinds(dolo) == ["worse"]
    assert "108" in last(dolo).text


def test_some_problem_asks_what_and_files_a_side_effect_with_the_patients_words(dolo):
    advance(dolo)
    receive(dolo, button="some_problem")
    assert dolo.awaiting.question == "side_effect_detail"
    receive(dolo, text="पेट में हल्की जलन है")
    side = [t for t in dolo.tasks if t.kind == "side_effect"]
    assert len(side) == 1 and "पेट में हल्की जलन है" in side[0].note
    assert any(a.quote == "पेट में हल्की जलन है" for r in dolo.records for a in r.answers)


def test_typed_answer_to_a_check_in_is_understood(dolo):
    advance(dolo)
    receive(dolo, text="koi dikkat nahi")
    receive(dolo, text="ab behtar hoon")
    assert [(a.question, a.value) for r in dolo.records for a in r.answers] == [
        ("tolerance", "no_problem"), ("symptom_status", "better")]


def test_unclear_typed_answer_asks_again_with_the_same_buttons(dolo):
    advance(dolo)
    receive(dolo, text="hmm")
    assert dolo.records[-1].action == "clarified"
    assert [b.id for b in last(dolo).buttons] == ["no_problem", "some_problem", "stopped"]


def test_two_unanswered_check_ins_stop_the_plan_and_tell_the_doctor(asthma):
    advance(asthma)
    advance(asthma)
    advance(asthma)
    assert task_kinds(asthma) == ["no_response"]
    assert all(t.status in ("sent", "expired", "skipped") for t in asthma.plan.touches[1:])
    assert advance(asthma) is False


def test_review_question_is_asked_with_the_confirmed_date(asthma):
    advance(asthma)
    receive(asthma, button="no_problem")
    advance(asthma)
    receive(asthma, button="better")
    receive(asthma, button="taking_all")
    assert "26 Oct" in last(asthma).text or "26-Oct" in last(asthma).text
    receive(asthma, button="need_another_day")
    assert task_kinds(asthma) == ["consult_request"]


# Red flags in a conversation

def test_red_flag_overrides_everything_and_ends_routine_check_ins(asthma):
    advance(asthma)
    receive(asthma, text="साँस बिल्कुल नहीं आ रही, बोल भी नहीं पा रही।")
    reply = last(asthma)
    assert reply.kind == "urgent" and reply.text == load_templates("hi-IN")["replies"]["urgent"].format(
        doctor=asthma.doctor_name)
    assert task_kinds(asthma) == ["urgent"]
    assert asthma.records[-1].red_flags == ["severe_breathlessness"]
    assert asthma.awaiting is None
    assert all(t.status != "planned" for t in asthma.plan.touches)


# Questions

def test_named_medicine_question_is_answered_from_its_fixed_row(asthma):
    receive(asthma, text="Inhaler दिन में कितनी बार ले सकते हैं?")
    reply = last(asthma)
    assert reply.kind == "answer" and reply.cites == ["rx2"]
    assert "ASTHALIN" in reply.text and "4" in reply.text
    assert asthma.records[-1].action == "answered" and asthma.tasks == []


def test_this_tablet_resolves_when_there_is_only_one_medicine(dolo):
    receive(dolo, text="ये गोली कितने दिन तक लेनी है?")
    assert last(dolo).kind == "answer" and "3 दिन" in last(dolo).text


@pytest.mark.parametrize("text", [
    "Wysolone अभी बंद कर दूँ?",
    "दर्द ज़्यादा है, क्या Montair दिन में दो बार ले लूँ?",
    "Can I take Crocin instead?",
    "what does my x-ray show?",
])
def test_change_or_unknown_questions_go_to_the_doctor(asthma, text):
    receive(asthma, text=text)
    assert last(asthma).text == load_templates("hi-IN")["replies"]["escalated"].format(doctor=asthma.doctor_name)
    assert task_kinds(asthma) == ["question"] and text in asthma.tasks[0].note


def test_doctor_keyword_and_new_consultation(asthma):
    receive(asthma, text="DOCTOR")
    receive(asthma, text="mujhe naya appointment chahiye")
    assert task_kinds(asthma) == ["callback", "consult_request"]


def test_stop_confirms_once_then_sends_nothing(asthma):
    receive(asthma, text="STOP")
    assert asthma.stopped and last(asthma).kind == "system"
    count = len(asthma.messages)
    assert advance(asthma) is False
    assert len(asthma.messages) == count
    assert "followup_whatsapp" not in asthma.consents


# The gate: sabotage

def test_answer_with_a_changed_dose_is_refused(asthma, visits):
    good = answer_medicine_question(visits["fam-010-a"].approved, load_templates("hi-IN"), "Montair कब लेनी है?")
    assert good is not None
    tampered = good.model_copy(update={"text": good.text.replace("1 गोली", "2 गोली")})
    assert tampered.text != good.text
    with pytest.raises(GateRefused):
        check_reply(asthma, visits["fam-010-a"].approved, tampered, red_flags=[])


def test_uncited_answer_is_refused(asthma, visits):
    good = answer_medicine_question(visits["fam-010-a"].approved, load_templates("hi-IN"), "Montair कब लेनी है?")
    with pytest.raises(GateRefused):
        check_reply(asthma, visits["fam-010-a"].approved, good.model_copy(update={"cites": []}), red_flags=[])


def test_softened_urgent_reply_is_refused(asthma, visits):
    receive(asthma, text="seene mein dard ho raha hai")
    softened = last(asthma).model_copy(update={"text": "Rest and drink water."})
    with pytest.raises(GateRefused):
        check_reply(asthma, visits["fam-010-a"].approved, softened, red_flags=["chest_pain"])


def test_reply_to_a_red_flag_must_be_urgent(asthma, visits):
    receive(asthma, text="Montair कब लेनी है?")
    with pytest.raises(GateRefused):
        check_reply(asthma, visits["fam-010-a"].approved, last(asthma), red_flags=["chest_pain"])


def test_draft_or_changed_report_never_reaches_the_patient(asthma, visits):
    changed = visits["fam-010-a"].approved.model_copy(update={"content_hash": "0" * 64})
    with pytest.raises(GateRefused, match="approved"):
        check_reply(asthma, changed, last(asthma), red_flags=[])


def test_scheduled_touch_outside_hours_is_refused(asthma, monkeypatch):
    night = datetime(2026, 10, 21, 23, 0, tzinfo=IST)
    asthma.plan.touches[1].due_at = night
    with pytest.raises(GateRefused, match="hours"):
        advance(asthma)
    assert conv_mod  # module stays importable for monkeypatching in later tests
