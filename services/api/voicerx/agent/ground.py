"""Answer a patient's question only when the approved record answers it: how, when or how long to take a
medicine the record names. Everything else goes to the doctor."""
from ..contracts.followup import Message
from ..pipeline.assemble import table_medicines
from .templates import answer_text, medicine_rows
from .text import contains, tokens, find

ASKS = ['kitna', 'kitni', 'kitne', 'kab', 'kaise', 'कितना', 'कितनी', 'कितने', 'कब', 'कैसे', 'how', 'when',
        'dose', 'बार', 'baar', 'din tak', 'दिन तक']
# Asking permission to change something is never answered by the agent.
CHANGES = ['ले लूं', 'ले लू', 'le lun', 'le loon', 'le lu', 'कर दूं', 'कर दू', 'kar dun', 'kar doon', 'kar du',
           'बंद', 'band', 'stop', 'छोड़', 'chhod', 'instead', 'जगह', 'jagah', 'should i', 'can i', 'shall i',
           'is it ok', 'chalega', 'चलेगा', 'double', 'बढ़ा', 'badha', 'kam kar', 'कम कर', 'again', 'dobara',
           'दोबारा', 'फिर से', 'start', 'शुरू', 'shuru', 'skip']
FORMS = {'tablet': ['tablet', 'goli', 'गोली', 'टैबलेट'], 'capsule': ['capsule', 'कैप्सूल'],
         'inhaler': ['inhaler', 'इनहेलर', 'pump', 'पंप'], 'syrup': ['syrup', 'सिरप'], 'gel': ['gel', 'जेल']}
GENERIC = ['dawa', 'dawai', 'दवा', 'दवाई', 'medicine', 'ये गोली', 'yeh goli', 'this tablet', 'this medicine']


def which_medicine(approved, text):
    medicines = [m for m in table_medicines(approved.checked) if m.match == 'exact' and m.product_id]
    words = tokens(text)
    named = []
    for rx in medicines:
        product = approved.products_used[rx.product_id]
        # The brand's first word alone ("Montair" for "Montair-LC") also names it; if two medicines share
        # that word, neither is chosen and the question goes to the doctor.
        names = {product.brand, tokens(product.brand)[0], rx.spoken_name, rx.quotes.get('name_quote', ''),
                 *product.aliases}
        if any(name and find(words, name) for name in names):
            named.append(rx)
    if not named:
        by_form = {}
        for rx in medicines:
            form = approved.products_used[rx.product_id].form
            if contains(text, FORMS.get(form, [form])):
                by_form.setdefault(form, []).append(rx)
        named = next(iter(by_form.values())) if len(by_form) == 1 else []
    if not named and len(medicines) == 1 and contains(text, GENERIC):
        named = medicines
    return named[0] if len(named) == 1 else None


def answer_medicine_question(approved, templates, text, at=None, message_id='draft', language=None):
    if contains(text, CHANGES) or not contains(text, ASKS):
        return None
    rx = which_medicine(approved, text)
    if rx is None:
        return None
    return answer_for(approved, templates, rx.id, at=at, message_id=message_id, language=language)


def answer_for(approved, templates, medicine_id, at=None, message_id='draft', language=None):
    """The fixed-row answer for a medicine already identified (by the rules above or a validated model
    reading, D-115). None when the id isn't an approved medicine."""
    rows = medicine_rows(approved, language)
    if medicine_id not in rows:
        return None
    from datetime import datetime, timezone
    return Message(id=message_id, sender='clinic', kind='answer', cites=[medicine_id],
                   text=answer_text(templates, rows[medicine_id]), at=at or datetime.now(timezone.utc))
