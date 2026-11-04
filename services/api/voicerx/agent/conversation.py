"""The follow-up conversation: send the plan's touches, read replies, record them, and hand the doctor
what needs a doctor. Buttons, keywords and fixed rules first (runbook D-104 to D-109); when the app passes an
`nlu` callable, a model's validated reading of free text is used where the rules don't decide (D-115). Every
reply is fixed text either way.

Order for each patient message: warning sign (rules), STOP, DOCTOR, warning sign (model, may only add),
side-effect detail, check-in answer, new consultation, medicine question, the model's reading, then ask again
(during a check-in) or pass to the doctor.
"""
from datetime import timedelta
from pathlib import Path

from ..contracts.followup import (Awaiting, Button, Conversation, DoctorTask, FollowUpAnswer, FollowUpRecord,
                                  Message)
from .gate import CONSENT, GateRefused, check_consent, check_reply, check_schedule, summary_names
from .ground import CHANGES, answer_for, answer_medicine_question
from .plan import plan_followups
from .redflags import find_red_flags
from .templates import SUPPORTED, format_date, load_templates, medicine_rows, summary_text
from .text import contains, find, negated, normalise, tokens

# The quick menu (D-117): attached to the summary, the greeting and "didn't understand" outside a check-in.
MENU = ['menu_medicines', 'menu_doctor', 'menu_report', 'menu_language', 'menu_stop']
# Typed answers to the first-message language question, before any model is asked.
LANGUAGE_WORDS = {'en-IN': ['english', 'angrezi', 'angreji', 'अंग्रेज़ी', 'अंग्रेजी', 'इंग्लिश'],
                  'hi-IN': ['hindi', 'हिंदी', 'हिन्दी']}
BUTTONS = {
    'tolerance': ['no_problem', 'some_problem', 'stopped'],
    'symptom_status': ['better', 'same', 'worse'],
    'adherence': ['taking_all', 'missed_some', 'stopped'],
    'review_attendance': ['yes', 'need_another_day'],
}
# Typed answers to a check-in. Pending language review, like the templates.
ANSWER_WORDS = {
    'tolerance': {
        'no_problem': ['no problem', 'koi dikkat nahi', 'koi dikkat nahin', 'कोई दिक्कत नहीं', 'कोई परेशानी नहीं',
                       'fine', 'theek', 'thik', 'ठीक', 'all good', 'sab theek'],
        'some_problem': ['problem', 'dikkat', 'दिक्कत', 'परेशानी', 'takleef', 'तकलीफ', 'side effect', 'ulti',
                         'उल्टी', 'chakkar', 'चक्कर', 'jalan', 'जलन', 'rash', 'दाने', 'khujli', 'खुजली'],
        'stopped': ['stopped', 'band kar', 'बंद कर', 'chhod', 'छोड़'],
    },
    'symptom_status': {
        'better': ['better', 'behtar', 'बेहतर', 'theek', 'thik', 'ठीक', 'aaram', 'आराम', 'fine', 'good'],
        'same': ['same', 'waisa hi', 'waise hi', 'वैसा ही', 'वैसे ही', 'no change', 'koi farak nahi', 'कोई फर्क नहीं'],
        'worse': ['worse', 'kharab', 'खराब', 'badh gaya', 'badh gayi', 'बढ़ गया', 'बढ़ गई', 'zyada', 'ज़्यादा', 'bura'],
    },
    'adherence': {
        'taking_all': ['yes', 'haan', 'han', 'हां', 'le raha', 'le rahi', 'ले रहा', 'ले रही', 'taking', 'sab le'],
        'missed_some': ['missed', 'miss', 'bhool', 'भूल', 'छूट', 'chhoot', 'chhut'],
        'stopped': ['stopped', 'band kar', 'बंद कर', 'chhod', 'छोड़'],
    },
    'review_attendance': {
        'yes': ['yes', 'haan', 'han', 'हां', 'aaunga', 'aaungi', 'आऊंगा', 'आऊंगी', 'aa jaunga', 'aa jaungi', 'ok',
                'okay', 'theek hai', 'ठीक है'],
        'need_another_day': ['another day', 'dusra din', 'doosra din', 'दूसरा दिन', 'nahi aa', 'नहीं आ',
                             'reschedule', 'change the date'],
    },
}
STOP_WORDS = {'stop', 'stop messages', 'unsubscribe', 'स्टॉप'}
DOCTOR_WORDS = {'doctor', 'dr', 'डॉक्टर', 'daktar'}
DOCTOR_PHRASES = ['doctor se baat', 'talk to the doctor', 'talk to doctor', 'speak to the doctor', 'डॉक्टर से बात',
                  'call me', 'call back', 'mujhe call']
CONSULT_PHRASES = ['appointment', 'अपॉइंटमेंट', 'new consultation', 'naya appointment', 'dikhana hai',
                   'दिखाना है', 'milna hai', 'book a visit']
ENGLISH = {'no_problem': 'no problem', 'some_problem': 'some problem', 'stopped': 'stopped the medicine',
           'better': 'better', 'same': 'the same', 'worse': 'worse', 'taking_all': 'taking all medicines',
           'missed_some': 'missed some doses', 'yes': 'will come', 'need_another_day': 'needs another day'}
STEP = timedelta(minutes=2)


def start(visit, conversation_id, ask_language: bool = False) -> Conversation:
    """Send the visit summary right after approval. Refuses without consent. With ask_language, a visit whose
    language isn't English first asks (in that language and English) which one to chat in; the summary
    follows the choice (D-116)."""
    check_consent(visit.consents)
    approved = visit.approved
    plan = plan_followups(visit)
    header = approved.header
    conv = Conversation(id=conversation_id, clinic_id=visit.clinic_id, case_id=visit.case_id,
                        patient_id=header.patient_id, patient_name=header.patient_name,
                        doctor_name=header.doctor_name, clinic_name=header.clinic_name,
                        language=approved.language_pref, visit_date=header.visit_date,
                        report_hash=approved.content_hash, consents=list(visit.consents), plan=plan,
                        clock=plan.touches[0].due_at)
    conv._visit = visit
    if ask_language and len(offered_languages(conv)) > 1:
        conv.language_chosen = False
        _send(conv, _language_prompt(conv))
    else:
        _send_summary(conv)
    return conv


def offered_languages(conv):
    """The visit's own language and English, where follow-up templates exist; the visit's language first."""
    return [lang for lang in dict.fromkeys([conv._visit.approved.language_pref, 'en-IN']) if lang in SUPPORTED]


def menu_buttons(templates):
    return [Button(id=b, label=templates['buttons'][b]) for b in MENU]


def _language_prompt(conv):
    native = load_templates(conv._visit.approved.language_pref)
    return Message(id='', sender='clinic', kind='question', at=conv.clock,
                   text=native['language_prompt'].format(**summary_names(conv)),
                   buttons=[Button(id=f'lang_{lang}', label=native['buttons'][f'lang_{lang}'])
                            for lang in offered_languages(conv)])


def _send_summary(conv):
    templates = load_templates(conv.language)
    summary = conv.plan.touches[0]
    _send(conv, Message(id='', sender='clinic', kind='summary', touch_id=summary.id, at=conv.clock,
                        text=summary_text(templates, conv._visit.approved, summary_names(conv), conv.language),
                        cites=list(medicine_rows(conv._visit.approved, conv.language)),
                        buttons=menu_buttons(templates)))
    summary.status = 'sent'


def attach(conv: Conversation, visit):
    """Reconnect a stored conversation to its visit (the approved report is not stored twice)."""
    conv._visit = visit
    return conv


def advance(conv: Conversation) -> bool:
    """Demo clock: jump to the next planned touch and send it. Returns False when nothing more will be sent."""
    if conv.stopped or not conv.language_chosen:
        return False
    if conv.awaiting is not None:
        touch = _touch(conv, conv.awaiting.touch_id)
        if touch.status == 'sent':
            touch.status = 'expired'
            conv.unanswered += 1
        conv.awaiting = None
        if conv.unanswered >= 2:
            _skip_planned(conv)
            _task(conv, 'no_response', None, 'Two check-ins in a row went unanswered. Follow-up messages stopped.')
            return False
    planned = sorted((t for t in conv.plan.touches if t.status == 'planned'), key=lambda t: t.due_at)
    if not planned:
        return False
    touch = planned[0]
    check_schedule(touch)
    conv.clock = max(conv.clock, touch.due_at)
    touch.status = 'sent'
    conv.awaiting = Awaiting(touch_id=touch.id, question=touch.questions[0], remaining=touch.questions[1:])
    _ask(conv, conv.awaiting.question, touch.id)
    return True


def receive(conv: Conversation, text: str | None = None, button: str | None = None,
            source: str = 'typed', nlu=None) -> FollowUpRecord:
    """source is 'typed', 'prisma' for a voice note's transcript, or 'call' for speech on a WhatsApp call;
    all go through the same rules. nlu(conv, text) -> Understanding | None reads free text with a model
    (agent/understand.py); None, or no nlu, leaves the rules alone."""
    conv.clock = conv.clock + STEP
    templates = load_templates(conv.language)
    replies = templates['replies']
    doctor = conv.doctor_name
    if button is not None:
        label = templates['buttons'].get(button, button)
        conv.messages.append(Message(id=f'm{len(conv.messages) + 1}', sender='patient', text=label, at=conv.clock,
                                     touch_id=conv.awaiting.touch_id if conv.awaiting else None))
        return _button(conv, button, label)
    text = (text or '').strip()
    conv.messages.append(Message(id=f'm{len(conv.messages) + 1}', sender='patient', text=text, at=conv.clock,
                                 touch_id=conv.awaiting.touch_id if conv.awaiting else None,
                                 voice=source in ('prisma', 'call')))
    said = _said(source)
    if not text:
        record = _record(conv, text, source, 'clarified', [])
        buttons = _buttons(templates, conv.awaiting.question) if conv.awaiting else []
        _reply(conv, record, 'question' if buttons else 'text', replies['not_heard'], buttons=buttons)
        return record
    conv.confirm_stop = False      # any new message answers a pending "stop?" question with "no"
    flags = find_red_flags(text)
    if flags:
        return _urgent(conv, text, source, flags)
    plain = ' '.join(tokens(text))
    if plain in {normalise(w) for w in STOP_WORDS}:
        return _stop(conv, text, source)
    if plain in {normalise(w) for w in DOCTOR_WORDS} or _has(text, DOCTOR_PHRASES):
        record = _record(conv, text, source, 'escalated', [])
        _task(conv, 'callback', record, f'Patient asked to speak to the clinic: «{text}».')
        _reply(conv, record, 'text', replies['callback'])
        return record
    reading = nlu(conv, text) if nlu and not conv.stopped else None
    if reading is not None and reading.warning_signs:     # a model may add a warning sign, never remove one
        return _urgent(conv, text, source, reading.warning_signs)
    if not conv.language_chosen:
        chosen = [lang for lang in offered_languages(conv) if contains(text, LANGUAGE_WORDS.get(lang, []))]
        if len(chosen) == 1:
            record = _record(conv, text, source, 'recorded', [])
            _set_language(conv, chosen[0], record)
            return record
    awaiting = conv.awaiting
    if awaiting and awaiting.question == 'side_effect_detail':
        answer = FollowUpAnswer(question='side_effect_detail', value='described', quote=text)
        record = _record(conv, text, source, 'recorded', [answer])
        _task(conv, 'side_effect', record, f'Problem with the new medicine. {said} «{text}».')
        _reply(conv, record, 'text', replies['side_effect_noted'].format(doctor=doctor))
        _next_question(conv)
        return record
    if awaiting:
        value = _read_answer(awaiting.question, text)
        if value:
            return _answer(conv, awaiting.question, value, text, source)
    if _has(text, CONSULT_PHRASES):
        record = _record(conv, text, source, 'escalated', [])
        _task(conv, 'consult_request', record, f'Patient asked for an appointment: «{text}».')
        _reply(conv, record, 'text', replies['consult'])
        return record
    answer = answer_medicine_question(conv._visit.approved, templates, text, at=conv.clock, language=conv.language)
    if answer is not None:
        record = _record(conv, text, source, 'answered', [])
        try:
            _reply(conv, record, 'answer', answer.text, cites=answer.cites)
            return record
        except GateRefused:
            conv.records.pop()  # nothing was sent; fall through to the doctor
    if reading is not None:
        record = _act(conv, reading, text, source)
        if record is not None:
            return record
    if awaiting:
        record = _record(conv, text, source, 'clarified', [])
        _reply(conv, record, 'question', replies['clarify'], buttons=_buttons(templates, awaiting.question))
        return record
    record = _record(conv, text, source, 'escalated', [])
    _task(conv, 'question', record, f'Question the approved visit does not answer: «{text}».')
    _reply(conv, record, 'text', replies['escalated'].format(doctor=doctor))
    return record


def _urgent(conv, text, source, flags):
    record = _record(conv, text, source, 'urgent', [], flags)
    conv.awaiting = None
    _skip_planned(conv)
    _task(conv, 'urgent', record, f'Warning sign ({", ".join(flags)}). {_said(source)} «{text}». '
                                  'Told to go to emergency or call 108.')
    _reply(conv, record, 'urgent', load_templates(conv.language)['replies']['urgent'].format(
        doctor=conv.doctor_name), flags)
    return record


def _escalate(conv, text, source, kind, note, reply):
    record = _record(conv, text, source, 'escalated', [])
    _task(conv, kind, record, note)
    _reply(conv, record, 'text', reply)
    return record


def _act(conv, reading, text, source):
    """Act on a validated model reading (agent/understand.py). Returns None to leave the message to the
    rules' fallback (ask again during a check-in, else pass to the doctor)."""
    templates = load_templates(conv.language)
    replies, doctor, said = templates['replies'], conv.doctor_name, _said(source)
    intent = reading.intent
    if intent == 'checkin_answer':           # validated: the value is one the awaited question accepts
        return _answer(conv, conv.awaiting.question, reading.answer_value, text, source)
    if intent == 'medicine_question' and not contains(text, CHANGES):
        answer = answer_for(conv._visit.approved, templates, reading.medicine_id, at=conv.clock,
                            language=conv.language)
        if answer is not None:
            record = _record(conv, text, source, 'answered', [])
            try:
                _reply(conv, record, 'answer', answer.text, cites=answer.cites)
                return record
            except GateRefused:
                conv.records.pop()
    if intent in ('medicine_question', 'change_request'):
        return _escalate(conv, text, source, 'question', f'Question the approved visit does not answer: «{text}».',
                         replies['escalated'].format(doctor=doctor))
    if intent == 'problem':
        return _escalate(conv, text, source, 'side_effect', f'Problem reported. {said} «{text}».',
                         replies['side_effect_noted'].format(doctor=doctor))
    if intent == 'appointment':
        return _escalate(conv, text, source, 'consult_request', f'Patient asked for an appointment: «{text}».',
                         replies['consult'])
    if intent == 'talk_to_doctor':
        return _escalate(conv, text, source, 'callback', f'Patient asked to speak to the clinic: «{text}».',
                         replies['callback'])
    record = _record(conv, text, source, 'clarified', [])
    if intent == 'stop':
        conv.confirm_stop = True
        _reply(conv, record, 'question', replies['stop_confirm'],
               buttons=[Button(id=b, label=templates['buttons'][b]) for b in ('stop_yes', 'stop_no')])
    elif intent == 'greeting':
        _reply(conv, record, 'text', replies['greeting'].format(doctor=doctor), buttons=menu_buttons(templates))
    elif intent == 'send_report':
        _reply(conv, record, 'text', replies['upload_hint'].format(doctor=doctor))
    elif intent == 'change_language':
        if reading.language:
            _set_language(conv, reading.language, record)
        else:
            _reply(conv, record, 'text', replies['language_unavailable'])
    else:
        conv.records.pop()
        return None
    return record


def _set_language(conv, language, record):
    """The patient's choice: the summary in that language if it hasn't gone out yet, else a confirmation."""
    conv.language, conv.language_chosen = language, True
    if conv.plan.touches[0].status == 'planned':
        _send_summary(conv)
    else:
        _reply(conv, record, 'text', load_templates(language)['replies']['language_set'])


def voice_not_used(conv: Conversation) -> FollowUpRecord:
    """A voice note that can't be transcribed (too long, unreadable, or voice is off): say so in fixed text,
    with no task for the doctor. Nothing of the audio is kept."""
    conv.clock = conv.clock + STEP
    conv.messages.append(Message(id=f'm{len(conv.messages) + 1}', sender='patient', text='', at=conv.clock,
                                 touch_id=conv.awaiting.touch_id if conv.awaiting else None, voice=True))
    record = _record(conv, '', None, 'clarified', [])
    _reply(conv, record, 'text', load_templates(conv.language)['replies']['voice_failed'])
    return record


def save(conv: Conversation, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{conv.id}.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(conv.model_dump_json(indent=2), encoding='utf-8')
    temporary.replace(path)


# Internals

def _touch(conv, touch_id):
    return next(t for t in conv.plan.touches if t.id == touch_id)


def _skip_planned(conv):
    for touch in conv.plan.touches:
        if touch.status == 'planned':
            touch.status = 'skipped'


def _has(text, phrases):
    words = tokens(text)
    return any(find(words, p) for p in phrases)


def _read_answer(question, text):
    """The single answer a typed reply gives, or None when it gives none, several, or a negated one."""
    words = tokens(text)
    matches = []
    for value, phrases in ANSWER_WORDS[question].items():
        for phrase in phrases:
            for span in find(words, phrase):
                matches.append((span, value, negated(words, span, phrase)))
    kept = [m for m in matches if not any(o[0][0] <= m[0][0] and m[0][1] <= o[0][1] and o[0] != m[0]
                                          for o in matches)]
    if not kept or any(neg for _, _, neg in kept):
        return None
    values = {value for _, value, _ in kept}
    return values.pop() if len(values) == 1 else None


def _buttons(templates, question):
    return [Button(id=b, label=templates['buttons'][b]) for b in BUTTONS.get(question, [])]


def _ask(conv, question, touch_id):
    templates = load_templates(conv.language)
    date = format_date(conv._visit.review_date) if conv._visit.review_date else ''
    _send(conv, Message(id='', sender='clinic', kind='question', touch_id=touch_id, at=conv.clock,
                        text=templates['questions'][question].format(date=date),
                        buttons=_buttons(templates, question)))


def _next_question(conv):
    awaiting = conv.awaiting
    if awaiting and awaiting.remaining:
        conv.awaiting = Awaiting(touch_id=awaiting.touch_id, question=awaiting.remaining[0],
                                 remaining=awaiting.remaining[1:])
        _ask(conv, conv.awaiting.question, awaiting.touch_id)
        return True
    conv.awaiting = None
    return False


def _button(conv, button, label):
    awaiting = conv.awaiting
    templates = load_templates(conv.language)
    if button in ('stop_yes', 'stop_no') and conv.confirm_stop:
        conv.confirm_stop = False
        if button == 'stop_yes':
            return _stop(conv, label, 'button')
        record = _record(conv, label, 'button', 'clarified', [])
        _reply(conv, record, 'text', templates['replies']['stop_cancelled'])
        return record
    if button.startswith('lang_') and button[len('lang_'):] in offered_languages(conv):
        record = _record(conv, label, 'button', 'recorded', [])
        _set_language(conv, button[len('lang_'):], record)
        return record
    if button in MENU:
        return _menu(conv, button, label, templates)
    if not awaiting or button not in BUTTONS.get(awaiting.question, []):
        record = _record(conv, label, 'button', 'clarified', [])
        _reply(conv, record, 'text', templates['replies']['clarify'],
               buttons=[] if awaiting else menu_buttons(templates))
        return record
    return _answer(conv, awaiting.question, button, label, 'button')


def _menu(conv, button, label, templates):
    replies, doctor = templates['replies'], conv.doctor_name
    if button == 'menu_doctor':
        return _escalate(conv, label, 'button', 'callback', 'Patient asked to speak to the clinic (menu).',
                         replies['callback'])
    record = _record(conv, label, 'button', 'answered' if button == 'menu_medicines' else 'clarified', [])
    if button == 'menu_medicines':
        _send_summary(conv)
    elif button == 'menu_report':
        _reply(conv, record, 'text', replies['upload_hint'].format(doctor=doctor))
    elif button == 'menu_language':
        _send(conv, _language_prompt(conv))
    else:   # menu_stop
        conv.confirm_stop = True
        _reply(conv, record, 'question', replies['stop_confirm'],
               buttons=[Button(id=b, label=templates['buttons'][b]) for b in ('stop_yes', 'stop_no')])
    return record


def _answer(conv, question, value, raw, source):
    templates = load_templates(conv.language)
    replies, doctor = templates['replies'], conv.doctor_name
    touch = _touch(conv, conv.awaiting.touch_id)
    touch.status = 'answered'
    conv.unanswered = 0
    answer = FollowUpAnswer(question=question, value=value, quote=raw if source != 'button' else None)
    record = _record(conv, raw, source, 'recorded', [answer])
    when = format_date(conv.clock.date())
    said = f' {_said(source)} «{raw}».' if source != 'button' else ''
    if value == 'some_problem':
        conv.awaiting = Awaiting(touch_id=touch.id, question='side_effect_detail',
                                 remaining=conv.awaiting.remaining)
        _ask(conv, 'side_effect_detail', touch.id)
        return record
    notable = None
    if value == 'worse':
        _task(conv, 'worse', record, f'Feels worse ({question.replace("_", " ")} check, {when}).{said}')
        notable = replies['worse'].format(doctor=doctor)
    elif value == 'stopped':
        _task(conv, 'stopped_medicine', record, f'Says they stopped a medicine ({when}).{said}')
        notable = replies['stopped_medicine'].format(doctor=doctor)
    elif value == 'need_another_day':
        _task(conv, 'consult_request', record, f'Cannot come for the review; needs another day ({when}).{said}')
        notable = replies['reschedule']
    if notable:
        _reply(conv, record, 'text', notable)
    if not _next_question(conv) and not notable:
        _reply(conv, record, 'text', replies['thanks'].format(doctor=doctor))
    return record


def _said(source):
    return {'prisma': 'Patient said in a voice note (Gnani Prisma transcript):',
            'call': 'Patient said on a WhatsApp call (Gnani Prisma transcript):'}.get(source, 'Patient wrote:')


def _stop(conv, text, source='typed'):
    record = _record(conv, text, source, 'stopped', [])
    conv.consents = [c for c in conv.consents if c != CONSENT]
    conv.awaiting = None
    _skip_planned(conv)
    conv.stopped = True
    _reply(conv, record, 'system', load_templates(conv.language)['replies']['stop_confirmed'])
    return record


def _record(conv, raw, source, action, answers, flags=()):
    touch_id = conv.awaiting.touch_id if conv.awaiting else None
    record = FollowUpRecord(id=f'{conv.id}-r{len(conv.records) + 1}', clinic_id=conv.clinic_id,
                            patient_id=conv.patient_id, visit_ref=conv.case_id, report_hash=conv.report_hash,
                            touch_id=touch_id, channel=conv.plan.channel, received_at=conv.clock, raw_text=raw,
                            transcript_source='prisma' if source == 'call' else source, answers=answers, red_flags=list(flags), action=action,
                            reply_text='')
    conv.records.append(record)
    return record


def _task(conv, kind, record, note):
    conv.tasks.append(DoctorTask(id=f'{conv.id}-k{len(conv.tasks) + 1}', kind=kind,
                                 record_id=record.id if record else None, patient_id=conv.patient_id,
                                 visit_ref=conv.case_id, created_at=conv.clock, note=note))


def _reply(conv, record, kind, text, flags=(), cites=(), buttons=()):
    message = Message(id='', sender='clinic', kind=kind, text=text, at=conv.clock, cites=list(cites),
                      buttons=list(buttons), touch_id=record.touch_id)
    _send(conv, message, flags)
    record.reply_text = (record.reply_text + '\n' + text).strip()
    record.reply_cites = list(dict.fromkeys(record.reply_cites + list(cites)))


def _send(conv, message, flags=()):
    """Everything sent to the patient goes through the gate first."""
    check_reply(conv, conv._visit.approved, message, list(flags))
    message.id = f'm{len(conv.messages) + 1}'
    conv.messages.append(message)
