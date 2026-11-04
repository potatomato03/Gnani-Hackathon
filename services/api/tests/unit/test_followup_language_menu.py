"""The first message asks for the patient's language (D-116); a quick menu works at any time (D-117)."""
from followup_helpers import dolo, fixed, last, medicine_id, task_kinds, visits  # noqa: F401
from voicerx.agent.conversation import MENU, advance, receive, start
from voicerx.agent.gate import summary_names
from voicerx.agent.templates import load_templates, medicine_rows, summary_text


def test_hindi_visit_asks_for_language_first_with_ai_disclosure(visits):
    conv = start(visits["fam-001-a"], "c1", ask_language=True)
    first = conv.messages[0]
    assert not conv.language_chosen and first.kind == "question"
    assert "AI" in first.text and [b.id for b in first.buttons] == ["lang_hi-IN", "lang_en-IN"]
    assert not any(m.kind == "summary" for m in conv.messages)
    assert advance(conv) is False                         # no check-in before the patient has chosen


def test_choosing_english_sends_the_english_summary_and_passes_the_gate(visits):
    conv = start(visits["fam-001-a"], "c1", ask_language=True)
    receive(conv, button="lang_en-IN")
    summary = last(conv)
    approved = conv._visit.approved
    assert conv.language == "en-IN" and conv.language_chosen and summary.kind == "summary"
    assert summary.text == summary_text(load_templates("en-IN"), approved, summary_names(conv), "en-IN")
    assert all(row.isascii() for row in medicine_rows(approved, "en-IN").values())
    assert conv.plan.touches[0].status == "sent"
    assert [b.id for b in summary.buttons] == MENU
    assert advance(conv) is True


def test_choosing_hindi_sends_todays_hindi_summary(visits):
    conv = start(visits["fam-001-a"], "c1", ask_language=True)
    receive(conv, button="lang_hi-IN")
    assert last(conv).text == start(visits["fam-001-a"], "c2").messages[0].text


def test_english_answers_use_the_english_row(visits):
    conv = start(visits["fam-001-a"], "c1", ask_language=True)
    receive(conv, button="lang_en-IN")
    rx = medicine_id(conv)
    receive(conv, text="how many times a day?", nlu=fixed(intent="medicine_question", medicine_id=rx,
                                                          quote="how many times"))
    assert medicine_rows(conv._visit.approved, "en-IN")[rx] in last(conv).text


def test_english_visit_skips_the_language_question(visits):
    conv = start(visits["fam-004-a"], "c2", ask_language=True)
    assert conv.language_chosen and conv.messages[0].kind == "summary"


def test_menu_buttons_work_outside_a_check_in(dolo):
    receive(dolo, button="menu_medicines")
    assert last(dolo).kind == "summary"
    receive(dolo, button="menu_doctor")
    assert "callback" in task_kinds(dolo)
    receive(dolo, button="menu_report")
    assert last(dolo).text == load_templates(dolo.language)["replies"]["upload_hint"].format(doctor=dolo.doctor_name)
    receive(dolo, button="menu_language")
    assert [b.id for b in last(dolo).buttons] == ["lang_hi-IN", "lang_en-IN"]
    receive(dolo, button="menu_stop")
    assert dolo.confirm_stop and [b.id for b in last(dolo).buttons] == ["stop_yes", "stop_no"]


def test_switching_language_later_does_not_resend_the_summary(dolo):
    receive(dolo, button="menu_language")
    receive(dolo, button="lang_en-IN")
    assert dolo.language == "en-IN" and last(dolo).text == load_templates("en-IN")["replies"]["language_set"]


def test_a_language_the_visit_does_not_offer_is_refused(visits):
    conv = start(visits["fam-004-a"], "c3", ask_language=True)
    record = receive(conv, button="lang_hi-IN")
    assert conv.language == "en-IN" and record.action == "clarified"


def test_typed_language_word_counts_as_a_choice(visits):
    conv = start(visits["fam-001-a"], "c3", ask_language=True)
    receive(conv, text="english please")
    assert conv.language == "en-IN" and conv.language_chosen and last(conv).kind == "summary"


def test_greeting_offers_the_menu(dolo):
    receive(dolo, text="namaste ji", nlu=fixed(intent="greeting", quote="namaste"))
    assert [b.id for b in last(dolo).buttons] == MENU



def test_a_warning_sign_in_the_language_answer_still_turns_urgent(visits):
    conv = start(visits["fam-001-a"], "c4", ask_language=True)
    record = receive(conv, text="hindi please, my lips are puffing up",
                     nlu=fixed(intent="change_language", language="hi-IN", warning_signs=["severe_allergy"],
                               quote="lips are puffing up"))
    assert record.action == "urgent" and last(conv).kind == "urgent"
