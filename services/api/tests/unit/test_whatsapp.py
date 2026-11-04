"""Real WhatsApp (Meta Cloud API) for private testing, against a fake Graph API: no network, no Meta account.

The test phone is 910000000001: an Indian mobile number can't start with 0, so it belongs to nobody.
"""
import hashlib
import hmac
import json
import logging
import struct
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from voicerx.agent.templates import load_templates
from voicerx.agent.voice import ogg_opus_seconds
from voicerx.agent.whatsapp import GraphClient, WhatsAppChannel, WhatsAppConfig, WhatsAppError
from voicerx.followup_api import create_app
from voicerx.ingest.gnani import Transcript

PHONE = "910000000001"
STRANGER = "910000000002"
SECRET = "test-app-secret"
TOKEN = "test-access-token"


def ogg_page(granule, packet, sequence, flags=0):
    segments = []
    remaining = len(packet)
    while remaining >= 255:
        segments.append(255)
        remaining -= 255
    segments.append(remaining)
    header = b"OggS" + bytes([0, flags]) + struct.pack("<qIII", granule, 1, sequence, 0) + bytes([len(segments)])
    return header + bytes(segments) + packet


def ogg_opus(seconds, pre_skip=312):
    """A minimal Ogg Opus stream: OpusHead, OpusTags, then one page whose granule gives the length."""
    head = b"OpusHead" + bytes([1, 1]) + struct.pack("<HIhB", pre_skip, 48000, 0, 0)
    return (ogg_page(0, head, 0, flags=2) + ogg_page(0, b"OpusTags" + b"\x00" * 8, 1)
            + ogg_page(int(seconds * 48000) + pre_skip, b"\x00" * 40, 2, flags=4))


class FakeGraph:
    """Stands in for graph.facebook.com and Meta's media host."""

    def __init__(self, media=b""):
        self.sent, self.uploads, self.calls = [], [], []
        self.media = media
        self.fail = None

    def __call__(self, method, url, headers, body):
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        path = urlparse(url).path
        if self.fail:
            return self.fail
        if method == "POST" and path.endswith("/messages"):
            self.sent.append(json.loads(body))
            return 200, {}, json.dumps({"messages": [{"id": f"wamid.{len(self.sent)}"}]}).encode()
        if method == "POST" and path.endswith("/media"):
            self.uploads.append(body)
            return 200, {}, b'{"id": "uploaded-1"}'
        if method == "POST" and path.endswith("/calls"):
            self.calls.append(json.loads(body))
            return 200, {}, b'{"success": true}'
        if method == "GET" and path.endswith("/media-in-1"):
            assert parse_qs(urlparse(url).query)["phone_number_id"] == ["pnid-1"]
            return 200, {}, b'{"url": "https://lookaside.example/media-in-1-download"}'
        if method == "GET" and path.endswith("/media-in-1-download"):
            return 200, {}, self.media
        return 404, {}, b'{"error": {"message": "unknown test route"}}'

    def texts(self):
        """Every message body sent, text or interactive (buttons, list)."""
        return [m["text"]["body"] if m["type"] == "text" else m["interactive"]["body"]["text"]
                for m in self.sent if m["type"] in ("text", "interactive")]


class Clock:
    def __init__(self):
        self.at = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.at


class FakeSpeech:
    name = "fake"

    def __init__(self, transcript=""):
        self.transcript, self.calls, self.languages = transcript, [], []

    def transcribe(self, audio, language_code, filename="voice-note.wav"):
        self.calls.append(("transcribe", filename, len(audio)))
        self.languages.append(language_code)
        return Transcript(text=self.transcript, detected_language=None, truncated=False)

    def synthesize(self, text, language, voice, container="mp3", sample_rate=24000):
        self.calls.append(("synthesize", text, container))
        return ogg_opus(1.0) if container == "ogg" else b"ID3-fake"


CONFIG = WhatsAppConfig(token=TOKEN, phone_number_id="pnid-1", app_secret=SECRET, verify_token="verify-me",
                        test_numbers=frozenset({PHONE}))


@pytest.fixture
def world(tmp_path):
    graph, clock, speech = FakeGraph(), Clock(), FakeSpeech()
    channel = WhatsAppChannel(CONFIG, GraphClient(CONFIG, transport=graph), now=clock)
    client = TestClient(create_app(tmp_path, speech=speech, whatsapp=channel))
    return client, graph, clock, speech, tmp_path


def post(client, value, secret=SECRET, field="messages"):
    body = json.dumps({"object": "whatsapp_business_account",
                       "entry": [{"id": "waba-1", "changes": [{"field": field, "value": value}]}]}).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/whatsapp/webhook", content=body,
                       headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"})


_ids = iter(range(1, 10_000))


def message(kind="text", sender=PHONE, mid=None, **content):
    item = {"from": sender, "id": mid or f"wamid.in.{next(_ids)}", "timestamp": "1762164000", "type": kind}
    if kind == "text":
        item["text"] = {"body": content["text"]}
    elif kind == "interactive" and "row" in content:
        item["interactive"] = {"type": "list_reply", "list_reply": {"id": content["row"], "title": "x"}}
    elif kind == "interactive":
        item["interactive"] = {"type": "button_reply", "button_reply": {"id": content["button"], "title": "x"}}
    elif kind == "audio":
        item["audio"] = {"id": "media-in-1", "mime_type": "audio/ogg; codecs=opus", "voice": True}
    return {"messaging_product": "whatsapp", "metadata": {"phone_number_id": "pnid-1"},
            "contacts": [{"wa_id": sender, "profile": {"name": "Tester"}}], "messages": [item]}


def join(client, case="fam-010-a", choose="native"):
    """JOIN a visit. The first message asks for the language (D-116); by default the patient picks the visit's
    own language, so the rest of the chat is as before. choose=None leaves the question open."""
    assert post(client, message(text=f"JOIN {case}")).status_code == 200
    visit = next(v for v in client.get("/visits").json() if v["case_id"] == case)
    if choose and not client.get(f"/conversations/{visit['conversation_id']}").json()["language_chosen"]:
        language = visit["language"] if choose == "native" else choose
        assert post(client, message(kind="interactive", button=f"lang_{language}")).status_code == 200
    return visit["conversation_id"]


# Webhook security

def test_verification_handshake(world):
    client = world[0]
    ok = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                                 "hub.challenge": "1158201444"})
    assert ok.status_code == 200 and ok.text == "1158201444"
    bad = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                                  "hub.challenge": "1158201444"})
    assert bad.status_code == 403


def test_whatsapp_is_off_without_config(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/health").json()["whatsapp"] == "off"
    assert client.get("/whatsapp/webhook", params={"hub.verify_token": "x"}).status_code == 404


def test_unsigned_or_wrongly_signed_posts_do_nothing(world):
    client, graph = world[0], world[1]
    assert post(client, message(text="JOIN fam-010-a"), secret="wrong").status_code == 401
    body = json.dumps({"entry": []}).encode()
    assert client.post("/whatsapp/webhook", content=body).status_code == 401
    assert graph.sent == []


def test_numbers_not_on_the_test_list_are_ignored(world):
    client, graph = world[0], world[1]
    post(client, message(text="JOIN fam-010-a", sender=STRANGER))
    assert graph.sent == []


def test_the_tunnel_reaches_only_the_webhook(world):
    client = world[0]
    outside = {"Cf-Connecting-Ip": "203.0.113.9"}
    assert client.get("/visits", headers=outside).status_code == 403
    assert client.post("/demo/reset", headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 403
    assert client.get("/whatsapp/webhook", headers=outside,
                      params={"hub.verify_token": "verify-me", "hub.challenge": "7"}).text == "7"
    assert client.get("/visits").status_code == 200   # local requests are unaffected


# Conversation over WhatsApp

def test_join_starts_the_visit_and_sends_the_summary(world):
    client, graph = world[0], world[1]
    conversation_id = join(client)
    conv = client.get(f"/conversations/{conversation_id}").json()
    assert conv["plan"]["channel"] == "whatsapp"
    assert [b["reply"]["id"] for b in graph.sent[0]["interactive"]["action"]["buttons"]] == ["lang_hi-IN", "lang_en-IN"]
    summary = graph.sent[1]
    assert summary["to"] == PHONE and summary["type"] == "interactive"
    assert summary["interactive"]["type"] == "list"         # five quick-menu buttons go as a list (D-117)
    first_summary = next(m for m in conv["messages"] if m["kind"] == "summary")
    assert summary["interactive"]["body"]["text"] == first_summary["text"] and "MONTAIR" in graph.texts()[1]
    rows = summary["interactive"]["action"]["sections"][0]["rows"]
    assert [r["id"] for r in rows] == [b["id"] for b in first_summary["buttons"]]
    assert all(len(r["title"]) <= 24 for r in rows) and len(summary["interactive"]["action"]["button"]) <= 20
    assert conv["contact"] and PHONE not in json.dumps(conv)


def test_an_unknown_phone_gets_the_join_help(world):
    client, graph = world[0], world[1]
    post(client, message(text="hello"))
    help_text = graph.texts()[0]
    assert len(graph.sent) == 1 and "JOIN fam-001-a" in help_text and "fam-010-a" in help_text
    assert "synthetic" in help_text.lower()


def test_check_in_goes_out_as_reply_buttons_and_a_tap_routes_as_a_button(world):
    client, graph = world[0], world[1]
    conversation_id = join(client)
    client.post(f"/conversations/{conversation_id}/advance")
    question = graph.sent[-1]
    assert question["type"] == "interactive" and question["interactive"]["type"] == "button"
    buttons = question["interactive"]["action"]["buttons"]
    assert [b["reply"]["id"] for b in buttons] == ["no_problem", "some_problem", "stopped"]
    post(client, message("interactive", button="stopped"))
    conv = client.get(f"/conversations/{conversation_id}").json()
    assert [t["kind"] for t in conv["tasks"]] == ["stopped_medicine"]
    assert conv["records"][-1]["channel"] == "whatsapp"
    assert graph.texts()[-1] == conv["messages"][-1]["text"]


def test_every_button_label_fits_whatsapp(world):
    for language in ("hi-IN", "en-IN"):
        for label in load_templates(language)["buttons"].values():
            assert len(label) <= 20, label


def test_a_warning_sign_gets_the_urgent_reply_and_an_urgent_task(world):
    client, graph = world[0], world[1]
    conversation_id = join(client)
    post(client, message(text="seene mein dard ho raha hai"))
    conv = client.get(f"/conversations/{conversation_id}").json()
    assert conv["messages"][-1]["kind"] == "urgent" and graph.texts()[-1] == conv["messages"][-1]["text"]
    assert client.get("/clinic/tasks").json()[0]["kind"] == "urgent"


def test_a_medicine_question_is_answered_from_the_approved_row(world):
    client, graph = world[0], world[1]
    join(client)
    post(client, message(text="Montair कब लेनी है?"))
    assert "MONTAIR" in graph.texts()[-1]


def test_meta_retries_are_processed_once(world):
    client, graph = world[0], world[1]
    join(client)
    before = len(graph.sent)
    item = message(text="DOCTOR", mid="wamid.same")
    post(client, item)
    post(client, item)
    assert len(graph.sent) == before + 1


def test_the_web_page_cannot_type_into_a_whatsapp_conversation(world):
    client = world[0]
    conversation_id = join(client)
    response = client.post(f"/conversations/{conversation_id}/messages", json={"text": "hi"})
    assert response.status_code == 409 and "phone" in response.json()["detail"]


# Voice notes over WhatsApp

def test_a_voice_note_goes_to_prisma_as_ogg_and_the_reply_comes_back_as_text_and_voice(world):
    client, graph, _, speech, _ = world
    graph.media = ogg_opus(2.0)
    speech.transcript = "Montair कब लेनी है?"
    conversation_id = join(client)
    post(client, message("audio"))
    assert ("transcribe", "voice-note.ogg", len(graph.media)) in speech.calls
    assert "MONTAIR" in graph.texts()[-1]
    audio = graph.sent[-1]
    assert audio["type"] == "audio" and audio["audio"] == {"id": "uploaded-1", "voice": True}
    assert b"audio/ogg" in graph.uploads[-1]
    conv = client.get(f"/conversations/{conversation_id}").json()
    assert [m for m in conv["messages"] if m["sender"] == "patient"][-1]["voice"] is True


def test_a_voice_note_over_30_seconds_is_refused_without_prisma(world):
    client, graph, _, speech, _ = world
    graph.media = ogg_opus(40.0)
    join(client)
    post(client, message("audio"))
    assert not any(c[0] == "transcribe" for c in speech.calls)
    assert graph.texts()[-1] == load_templates("hi-IN")["replies"]["voice_failed"]


def test_ogg_opus_length_is_read_from_the_last_page():
    assert ogg_opus_seconds(ogg_opus(2.5)) == pytest.approx(2.5)
    with pytest.raises(ValueError):
        ogg_opus_seconds(b"not ogg at all")


# Delivery rules

def test_nothing_is_sent_outside_the_24_hour_window_until_the_patient_writes(world):
    client, graph, clock, _, _ = world
    conversation_id = join(client)
    sent = len(graph.sent)
    clock.at += timedelta(hours=25)
    conv = client.post(f"/conversations/{conversation_id}/advance").json()
    assert "24-hour" in conv["delivery"] and len(graph.sent) == sent
    post(client, message(text="theek hoon"))
    assert graph.sent[sent]["type"] == "interactive"     # the held check-in goes out first
    assert len(graph.sent) > sent + 1


def test_after_a_restart_delivery_waits_for_the_phone(world):
    client, graph, clock, speech, state = world
    conversation_id = join(client)
    sent = len(graph.sent)
    fresh = WhatsAppChannel(CONFIG, GraphClient(CONFIG, transport=graph), now=clock)
    again = TestClient(create_app(state, speech=speech, whatsapp=fresh))
    conv = again.post(f"/conversations/{conversation_id}/advance").json()
    assert "waiting for the phone" in conv["delivery"] and len(graph.sent) == sent
    post(again, message(text="theek hoon"))
    assert graph.sent[sent]["type"] == "interactive"


def test_the_phone_number_is_never_written_or_logged(world, caplog):
    client, graph, _, _, state = world
    caplog.set_level(logging.DEBUG)
    join(client)
    post(client, message(text="DOCTOR"))
    graph.fail = (400, {}, json.dumps({"error": {"message": f"bad recipient {PHONE} token {TOKEN}"}}).encode())
    post(client, message(text="theek hoon"))
    for path in state.rglob("*"):
        if path.is_file():
            assert PHONE.encode() not in path.read_bytes(), path
    assert PHONE not in caplog.text and TOKEN not in caplog.text


def test_graph_errors_hide_the_token_and_numbers():
    graph = FakeGraph()
    graph.fail = (400, {}, json.dumps({"error": {"message": f"bad {PHONE} {TOKEN}"}}).encode())
    with pytest.raises(WhatsAppError) as error:
        GraphClient(CONFIG, transport=graph).send_text(PHONE, "hello")
    assert PHONE not in str(error.value) and TOKEN not in str(error.value) and "400" in str(error.value)
    assert TOKEN not in repr(CONFIG) and SECRET not in repr(CONFIG)


def test_the_web_page_opens_the_newest_conversation_for_a_visit(world):
    client = world[0]
    visit = next(v for v in client.get("/visits").json() if v["case_id"] == "fam-010-a")
    simulated = client.post(f"/visits/{visit['visit_id']}/start").json()
    conversation_id = join(client)
    assert conversation_id != simulated["id"]
    opened = client.post(f"/visits/{visit['visit_id']}/start").json()
    assert opened["id"] == conversation_id and opened["plan"]["channel"] == "whatsapp"


# Voice calls (Phase B, D-114): an in-process WebRTC loopback, where a second aiortc peer plays Meta and the caller

import asyncio  # noqa: E402
import fractions  # noqa: E402
import io  # noqa: E402
import math  # noqa: E402
import queue  # noqa: E402
import time  # noqa: E402
import wave  # noqa: E402








def call_event(event, call_id, sdp=None, sender=PHONE):
    item = {"id": call_id, "from": sender, "to": "15550000000", "event": event, "timestamp": "1762164000"}
    if sdp:
        item["session"] = {"sdp_type": "offer", "sdp": sdp}
    return {"messaging_product": "whatsapp", "metadata": {"phone_number_id": "pnid-1",
                                                          "display_phone_number": "15550000000"},
            "contacts": [{"wa_id": sender}], "calls": [item]}




def test_calls_from_unknown_or_unbound_numbers_are_rejected(world):
    client, graph = world[0], world[1]
    post(client, call_event("connect", "wacid.2", "v=0", sender=STRANGER), SECRET, "calls")
    post(client, call_event("connect", "wacid.3", "v=0"), SECRET, "calls")     # allowed, but never sent JOIN
    assert [c["action"] for c in graph.calls] == ["reject", "reject"]
    assert "JOIN" in graph.texts()[-1]


def test_enable_calling_switches_calling_on_for_the_number():
    sent = []

    def transport(method, url, headers, body):
        sent.append((method, urlparse(url).path, json.loads(body)))
        return 200, {}, b'{"success": true}'

    GraphClient(CONFIG, transport=transport).enable_calling()
    assert sent == [("POST", "/v26.0/pnid-1/settings",
                     {"calling": {"status": "ENABLED", "call_icon_visibility": "DEFAULT"}})]



# Conversational bot (D-115 to D-118): the model's reading, the language question, the menu list, memory

from voicerx.agent.memory import LocalMemoryStore, patient_key_for_number  # noqa: E402
from voicerx.contracts.followup import Understanding  # noqa: E402

HASH_KEY = "test-patient-hash-key"


class Talk:
    """A WhatsApp test world with patient memory and a stub model whose reading each test sets."""

    def __init__(self, tmp_path):
        self.graph, self.clock, self.speech = FakeGraph(), Clock(), FakeSpeech()
        self.memory = LocalMemoryStore(tmp_path / "memory")
        self.reading, self.reader = None, None
        channel = WhatsAppChannel(CONFIG, GraphClient(CONFIG, transport=self.graph), now=self.clock,
                                  hash_key=HASH_KEY)
        self.client = TestClient(create_app(tmp_path, speech=self.speech, whatsapp=channel, memory=self.memory,
                                            nlu=lambda conv, text: self.reading,
                                            reader=lambda data, mime: self.reader(data, mime)))
        self.patient_key = patient_key_for_number(PHONE, HASH_KEY)

    def reads(self, **fields):
        base = dict(intent="other", answer_value=None, medicine_id=None, language=None, warning_signs=[], quote="")
        self.reading = Understanding(**{**base, **fields})

    def tasks(self):
        conv_id = next(v for v in self.client.get("/visits").json() if v["case_id"] == "fam-001-a")["conversation_id"]
        return [t["kind"] for t in self.client.get(f"/conversations/{conv_id}").json()["tasks"]]


@pytest.fixture
def talk(tmp_path):
    return Talk(tmp_path)


def choose_english(talk):
    assert post(talk.client, message(kind="interactive", button="lang_en-IN")).status_code == 200


def test_join_asks_for_the_language_with_two_buttons(talk):
    join(talk.client, "fam-001-a", choose=None)
    first = talk.graph.sent[0]
    assert first["interactive"]["type"] == "button"
    assert [b["reply"]["id"] for b in first["interactive"]["action"]["buttons"]] == ["lang_hi-IN", "lang_en-IN"]
    choose_english(talk)
    summary = talk.graph.sent[-1]
    assert summary["interactive"]["type"] == "list" and "Your doctor prescribed" in summary["interactive"]["body"]["text"]


def test_list_reply_works_as_a_menu_tap(talk):
    join(talk.client, "fam-001-a", choose=None)
    choose_english(talk)
    post(talk.client, message(kind="interactive", row="menu_doctor"))
    assert "callback" in talk.tasks()


def test_records_reach_memory_once_under_the_patient_key(talk, tmp_path):
    join(talk.client, "fam-001-a", choose=None)
    choose_english(talk)
    talk.reads(intent="problem", quote="I feel dizzy")
    post(talk.client, message(text="I feel dizzy after the tablet"))
    talk.reads(intent="greeting", quote="thanks")
    post(talk.client, message(text="thanks"))
    items = talk.memory.recent(talk.patient_key)
    assert [i.kind for i in items].count("problem") == 1 and items[0].quote == "I feel dizzy after the tablet"
    assert PHONE not in "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "memory").rglob("*.jsonl"))


def test_voice_note_transcript_goes_through_the_model(talk):
    join(talk.client, "fam-001-a", choose=None)
    choose_english(talk)
    talk.graph.media = ogg_opus(2.0)
    talk.speech.transcript = "the medicine makes me dizzy"
    talk.reads(intent="problem", quote="makes me dizzy")
    post(talk.client, message(kind="audio"))
    assert "side_effect" in talk.tasks() and talk.speech.languages[-1] == "en-IN,hi-IN"


def test_patient_key_survives_app_secret_rotation():
    rotated = WhatsAppConfig(token=TOKEN, phone_number_id="pnid-1", app_secret="another-secret",
                             verify_token="verify-me", test_numbers=frozenset({PHONE}))
    a = WhatsAppChannel(CONFIG, GraphClient(CONFIG), hash_key="h").contact(PHONE)
    b = WhatsAppChannel(rotated, GraphClient(rotated), hash_key="h").contact(PHONE)
    assert a == b == patient_key_for_number(PHONE, "h")


def test_images_and_documents_are_parsed_with_their_type():
    from voicerx.agent.whatsapp import parse_webhook
    value = message(kind="image")
    value["messages"][0]["image"] = {"id": "media-img", "mime_type": "image/jpeg", "sha256": "x"}
    doc = message(kind="document")
    doc["messages"][0]["document"] = {"id": "media-doc", "mime_type": "application/pdf", "filename": "cbc.pdf"}
    payload = {"entry": [{"changes": [{"value": value}, {"value": doc}]}]}
    image, document = parse_webhook(payload)[0]
    assert (image.kind, image.media_id, image.mime) == ("image", "media-img", "image/jpeg")
    assert (document.kind, document.media_id, document.mime) == ("document", "media-doc", "application/pdf")



def test_a_report_pdf_is_read_saved_and_sent_to_the_doctor(talk, tmp_path):
    from voicerx.contracts.documents import ReportFinding, ReportReading
    join(talk.client, "fam-001-a", choose="en-IN")
    talk.graph.media = b"%PDF-1.4 synthetic report"
    seen = []

    def reader(data, mime):
        seen.append((data, mime))
        return (ReportReading(is_medical_report=True, report_type="Complete blood count", report_date=None,
                              transcription="Hb 10.2 g/dL", medicines_named=[],
                              findings=[ReportFinding(name="Hb", value="10.2", unit="g/dL", reference_range=None,
                                                      flag="low", quote="Hb 10.2")]), "gemini_vision", 1)

    talk.reader = reader
    doc = message(kind="document")
    doc["messages"][0]["document"] = {"id": "media-in-1", "mime_type": "application/pdf", "filename": "cbc.pdf"}
    post(talk.client, doc)
    assert seen == [(b"%PDF-1.4 synthetic report", "application/pdf")]
    assert "document" in talk.tasks() and "Complete blood count" not in talk.graph.texts()[-1]   # model text: doctor only
    memory = talk.client.get(f"/patients/{talk.patient_key}/memory").json()
    assert memory["documents"][0]["reading"]["findings"][0]["flag"] == "low"
    assert [i["kind"] for i in memory["items"]].count("document_fact") == 1
    assert not any(p.suffix == ".pdf" for p in tmp_path.rglob("*") if "visits" not in p.parts)   # file never kept
