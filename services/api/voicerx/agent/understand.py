"""Read a patient's message with a model into a fixed schema (runbook D-115): the model reads, code speaks.

The model only classifies. Its output is enum values, ids from lists we give it, and a quote that must be in the
message. Code validates all of it here, and nothing the model writes is ever sent to the patient.
"""
import json
from pathlib import Path

from ..contracts.followup import Conversation, MemoryItem, Understanding
from ..llm.client import ModelOutputInvalid, QuotaExhausted
from ..pipeline.assemble import table_medicines
from .conversation import BUTTONS
from .redflags import load_rules
from .templates import SUPPORTED
from .text import find, tokens

PROMPT_VERSION = 'understand-v1'
SYSTEM = (Path(__file__).parent / 'prompts' / 'understand.md').read_text(encoding='utf-8')
MEMORY_ITEMS = 20


def _medicines(conv):
    approved = conv._visit.approved
    return [rx for rx in table_medicines(approved.checked) if rx.match == 'exact' and rx.product_id]


def _flag_ids():
    return {flag['id'] for flag in load_rules()['flags']}


def offered_languages(conv):
    """The visit's own language and English, where follow-up templates exist (D-116)."""
    return {conv._visit.approved.language_pref, 'en-IN'} & set(SUPPORTED)


def _quoted(text, quote):
    return bool(tokens(quote)) and bool(find(tokens(text), quote))


def validate(u: Understanding, conv: Conversation, text: str) -> Understanding | None:
    """None when the quote isn't in the message; otherwise the reading with every value the conversation
    doesn't allow removed."""
    if not _quoted(text, u.quote):
        return None
    changes = {'warning_signs': [f for f in dict.fromkeys(u.warning_signs) if f in _flag_ids()]}
    if u.medicine_id not in {rx.id for rx in _medicines(conv)}:
        changes['medicine_id'] = None
        if u.intent == 'medicine_question':
            changes['intent'] = 'other'
    awaiting = conv.awaiting
    if u.intent == 'checkin_answer' and not (awaiting and u.answer_value in BUTTONS.get(awaiting.question, [])):
        changes.update(intent='other', answer_value=None)
    if u.language not in offered_languages(conv):
        changes['language'] = None
    return u.model_copy(update=changes)


def _payload(conv, text, memory):
    products = conv._visit.approved.products_used
    awaiting = conv.awaiting
    return {
        'awaiting_question': awaiting.question if awaiting else None,
        'allowed_answers': BUTTONS.get(awaiting.question, []) if awaiting else [],
        'medicines': [{'id': rx.id, 'brand': products[rx.product_id].brand, 'spoken_name': rx.spoken_name}
                      for rx in _medicines(conv)],
        'warning_sign_ids': sorted(_flag_ids()),
        'languages_offered': sorted(offered_languages(conv)),
        'recent_memory': [{'kind': m.kind, 'text': m.text, 'at': m.at.isoformat()} for m in memory[-MEMORY_ITEMS:]],
        'message': text,
    }


def understand(client, conv: Conversation, text: str, memory: list[MemoryItem]) -> Understanding | None:
    """The validated reading, or None when no model answered or its answer didn't hold up."""
    try:
        reading, _ = client.generate(SYSTEM, json.dumps(_payload(conv, text, memory), ensure_ascii=False),
                                     Understanding, PROMPT_VERSION)
    except (QuotaExhausted, ModelOutputInvalid):
        return None
    return validate(reading, conv, text)


def make_nlu(client, memory_store=None):
    """The callable the app hands to conversation.receive."""
    def nlu(conv, text):
        memory = memory_store.recent(conv.patient_key, MEMORY_ITEMS) if memory_store and conv.patient_key else []
        return understand(client, conv, text, memory)
    return nlu
