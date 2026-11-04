"""Free text read by a model (stubbed here), routed by code: rules first, fixed replies only (runbook D-115)."""
from followup_helpers import (dolo, dolo_awaiting_symptom_status, fixed, last, medicine_id, task_kinds,  # noqa: F401
                              visits)
from voicerx.agent.conversation import receive
from voicerx.agent.templates import load_templates


def replies(conv):
    return load_templates(conv.language)["replies"]


def test_receive_falls_back_to_rules_when_understanding_is_none(dolo):
    record = receive(dolo, text="kya main ye dawai khaane ke baad le sakta hoon", nlu=lambda c, t: None)
    assert record.action == "escalated" and task_kinds(dolo) == ["question"]


def test_no_nlu_is_exactly_todays_behaviour(dolo):
    record = receive(dolo, text="pehle se kaafi aaram hai")
    assert record.action == "escalated"


def test_free_text_checkin_answer_is_recorded(dolo_awaiting_symptom_status):
    conv = dolo_awaiting_symptom_status
    record = receive(conv, text="bukhar utar gaya hai", nlu=fixed(intent="checkin_answer", answer_value="better",
                                                                  quote="bukhar utar gaya"))
    assert record.answers[0].value == "better" and record.action == "recorded"


def test_the_rules_alone_cannot_read_that_answer(dolo_awaiting_symptom_status):
    assert receive(dolo_awaiting_symptom_status, text="bukhar utar gaya hai").action == "clarified"


def test_model_warning_sign_raises_urgency_over_rule_answer(dolo_awaiting_symptom_status):
    conv = dolo_awaiting_symptom_status
    record = receive(conv, text="better, but my lips are puffing up",
                     nlu=fixed(intent="checkin_answer", answer_value="better", warning_signs=["severe_allergy"],
                               quote="lips are puffing up"))
    assert record.action == "urgent" and record.red_flags == ["severe_allergy"]
    assert "urgent" in task_kinds(conv) and last(conv).kind == "urgent"


def test_rule_red_flag_wins_when_model_says_greeting(dolo):
    record = receive(dolo, text="hello, I have chest pain", nlu=fixed(intent="greeting", quote="hello"))
    assert record.action == "urgent" and record.red_flags == ["chest_pain"]


def test_medicine_question_gets_the_exact_row_and_change_requests_go_to_the_doctor(dolo):
    rx = medicine_id(dolo)
    asked = receive(dolo, text="bukhar wali goli din mein kitni baar?",
                    nlu=fixed(intent="medicine_question", medicine_id=rx, quote="kitni baar"))
    assert asked.action == "answered" and last(dolo).cites == [rx] and last(dolo).kind == "answer"
    change = receive(dolo, text="kya main dolo band kar doon?",
                     nlu=fixed(intent="medicine_question", medicine_id=rx, quote="band kar doon"))
    assert change.action == "escalated" and task_kinds(dolo) == ["question"]


def test_change_request_is_escalated_even_during_a_check_in(dolo_awaiting_symptom_status):
    conv = dolo_awaiting_symptom_status
    record = receive(conv, text="dawai double kar sakta hoon?", nlu=fixed(intent="change_request", quote="double"))
    assert record.action == "escalated" and "question" in task_kinds(conv)


def test_problem_appointment_and_doctor_open_the_right_tasks(dolo):
    receive(dolo, text="is dawai se pet mein jalan ho rahi hai", nlu=fixed(intent="problem", quote="pet mein jalan"))
    assert last(dolo).text == replies(dolo)["side_effect_noted"].format(doctor=dolo.doctor_name)
    receive(dolo, text="mujhe agle hafte milna hai", nlu=fixed(intent="appointment", quote="milna hai"))
    receive(dolo, text="please ask someone to ring me", nlu=fixed(intent="talk_to_doctor", quote="ring me"))
    assert task_kinds(dolo) == ["side_effect", "consult_request", "callback"]


def test_model_stop_asks_for_confirmation_but_the_word_stop_does_not(dolo):
    receive(dolo, text="please don't message me anymore", nlu=fixed(intent="stop", quote="don't message me"))
    assert not dolo.stopped and dolo.confirm_stop
    assert [b.id for b in last(dolo).buttons] == ["stop_yes", "stop_no"]
    receive(dolo, button="stop_yes")
    assert dolo.stopped and not dolo.confirm_stop


def test_stop_confirmation_can_be_declined(dolo):
    receive(dolo, text="no more messages", nlu=fixed(intent="stop", quote="no more messages"))
    receive(dolo, button="stop_no")
    assert not dolo.stopped and not dolo.confirm_stop
    assert last(dolo).text == replies(dolo)["stop_cancelled"]


def test_greeting_report_and_language_get_fixed_replies(dolo):
    receive(dolo, text="namaste", nlu=fixed(intent="greeting", quote="namaste"))
    assert last(dolo).text == replies(dolo)["greeting"].format(doctor=dolo.doctor_name)
    receive(dolo, text="mere paas purani report hai", nlu=fixed(intent="send_report", quote="purani report"))
    assert last(dolo).text == replies(dolo)["upload_hint"].format(doctor=dolo.doctor_name)
    receive(dolo, text="english mein baat karo", nlu=fixed(intent="change_language", language="en-IN",
                                                          quote="english"))
    assert dolo.language == "en-IN" and last(dolo).text == replies(dolo)["language_set"]
    receive(dolo, text="tamil please", nlu=fixed(intent="change_language", language=None, quote="tamil"))
    assert last(dolo).text == replies(dolo)["language_unavailable"]
    assert task_kinds(dolo) == []



def test_the_model_is_not_asked_after_stop(dolo):
    from voicerx.agent.gate import GateRefused
    receive(dolo, text="STOP")
    asked = []
    try:
        receive(dolo, text="how are you", nlu=lambda conv, text: asked.append(text))
    except GateRefused:
        pass
    assert asked == []
