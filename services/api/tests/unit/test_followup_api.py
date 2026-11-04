import pytest
from fastapi.testclient import TestClient

from voicerx.app import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    return TestClient(create_app(tmp_path_factory.mktemp("followup-demo")))


def test_lists_the_three_synthetic_demo_visits(client):
    visits = client.get("/demo/visits").json()
    assert [v["case_id"] for v in visits] == ["fam-001-a", "fam-004-a", "fam-010-a"]
    assert all(v["synthetic"] is True for v in visits)
    assert visits[2]["language"] == "hi-IN" and visits[2]["medicines"]


def test_full_flow_from_summary_to_doctor_task(client):
    conv = client.post("/demo/visits/fam-001-a/start").json()
    assert conv["synthetic"] is True and conv["messages"][0]["kind"] == "summary"
    conv = client.post(f"/conversations/{conv['id']}/advance").json()
    assert [b["id"] for b in conv["messages"][-1]["buttons"]] == ["no_problem", "some_problem", "stopped"]
    conv = client.post(f"/conversations/{conv['id']}/messages", json={"button": "no_problem"}).json()
    conv = client.post(f"/conversations/{conv['id']}/messages", json={"button": "worse"}).json()
    assert [t["kind"] for t in conv["tasks"]] == ["worse"]
    stored = client.get(f"/conversations/{conv['id']}").json()
    assert stored["messages"] == conv["messages"]
    tasks = client.get("/clinic/tasks").json()
    assert any(t["kind"] == "worse" and t["conversation_id"] == conv["id"] and t["patient_name"] for t in tasks)


def test_red_flag_through_the_api_puts_an_urgent_task_first(client):
    first = client.post("/demo/visits/fam-001-a/start").json()
    client.post(f"/conversations/{first['id']}/messages", json={"text": "DOCTOR"})
    conv = client.post("/demo/visits/fam-010-a/start").json()
    conv = client.post(f"/conversations/{conv['id']}/messages", json={"text": "seene mein dard ho raha hai"}).json()
    assert conv["messages"][-1]["kind"] == "urgent"
    assert client.get("/clinic/tasks").json()[0]["kind"] == "urgent"


def test_bad_requests_are_refused(client):
    assert client.post("/demo/visits/fam-999/start").status_code == 404
    assert client.get("/conversations/nope").status_code == 404
    conv = client.post("/demo/visits/fam-004-a/start").json()
    assert client.post(f"/conversations/{conv['id']}/messages", json={}).status_code == 422
    assert client.post(f"/conversations/{conv['id']}/messages", json={"text": "x" * 2001}).status_code == 422


def test_nothing_more_to_send_is_reported_not_faked(client):
    conv = client.post("/demo/visits/fam-004-a/start").json()
    response = client.post(f"/conversations/{conv['id']}/advance")
    assert response.status_code == 200 and response.json()["advanced"] is False


def test_reset_clears_every_conversation_and_task(client):
    conv = client.post("/demo/visits/fam-010-a/start").json()
    client.post(f"/conversations/{conv['id']}/messages", json={"text": "DOCTOR"})
    assert client.get("/clinic/tasks").json()
    assert client.post("/demo/reset").json() == {"reset": True}
    assert client.get("/clinic/tasks").json() == []
    assert client.get(f"/conversations/{conv['id']}").status_code == 404


def test_saved_conversations_survive_an_api_restart(tmp_path):
    first = TestClient(create_app(tmp_path))
    conv = first.post("/demo/visits/fam-001-a/start").json()
    first.post(f"/conversations/{conv['id']}/messages", json={"text": "DOCTOR"})
    again = TestClient(create_app(tmp_path))
    assert [t["kind"] for t in again.get("/clinic/tasks").json()] == ["callback"]
    assert again.get(f"/conversations/{conv['id']}").json()["messages"] == \
        first.get(f"/conversations/{conv['id']}").json()["messages"]


# Voice and approved visits

import io  # noqa: E402
import wave  # noqa: E402

from voicerx.ingest.fake_speech import FakeSpeech  # noqa: E402


def clip(seconds=1.0):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x00\x00" * int(seconds * 16000))
    return buffer.getvalue()


@pytest.fixture
def voiced(tmp_path):
    speech = FakeSpeech()
    return TestClient(create_app(tmp_path, speech=speech)), speech, tmp_path


def test_health_says_whether_voice_is_on(tmp_path, voiced):
    assert TestClient(create_app(tmp_path / "off", speech=None)).get("/health").json()["speech"] == "off"
    assert voiced[0].get("/health").json()["speech"] == "fake"


def test_voice_endpoints_are_off_without_a_key(tmp_path):
    client = TestClient(create_app(tmp_path, speech=None))
    conv = client.post("/demo/visits/fam-010-a/start").json()
    first = conv["messages"][0]["id"]
    assert client.post(f"/conversations/{conv['id']}/messages/{first}/voice").status_code == 503
    assert client.post(f"/conversations/{conv['id']}/voice", content=clip()).status_code == 503
    assert client.post(f"/conversations/{conv['id']}/voice/synthetic", json={"text": "DOCTOR"}).status_code == 503


def test_listen_synthesises_once_and_serves_the_audio(voiced):
    client, speech, _ = voiced
    conv = client.post("/demo/visits/fam-010-a/start").json()
    first = conv["messages"][0]["id"]
    played = client.post(f"/conversations/{conv['id']}/messages/{first}/voice").json()
    assert played["cached"] is False and played["audio_url"].startswith("/audio/")
    again = client.post(f"/conversations/{conv['id']}/messages/{first}/voice").json()
    assert again == {**played, "cached": True}
    assert [c[0] for c in speech.calls] == ["synthesize"]
    audio = client.get(played["audio_url"])
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"   # fake returns WAV
    stored = client.get(f"/conversations/{conv['id']}").json()
    assert stored["messages"][0]["audio_id"] == played["audio_url"][7:-4]
    assert client.get("/audio/../../etc/passwd").status_code == 404
    assert client.get("/audio/" + "z" * 32 + ".mp3").status_code == 404


def test_recorded_voice_note_is_transcribed_and_never_stored(voiced):
    client, speech, state = voiced
    speech.transcript = "seene mein dard ho raha hai"
    conv = client.post("/demo/visits/fam-010-a/start").json()
    conv = client.post(f"/conversations/{conv['id']}/voice", content=clip(),
                       headers={"Content-Type": "audio/wav"}).json()
    patient = [m for m in conv["messages"] if m["sender"] == "patient"][-1]
    assert patient["voice"] is True and conv["messages"][-1]["kind"] == "urgent"
    assert conv["records"][-1]["transcript_source"] == "prisma"
    assert not [p for p in state.rglob("*") if p.suffix in (".wav", ".webm", ".ogg")]


def test_bad_voice_notes_are_refused(voiced):
    client, _, _ = voiced
    conv = client.post("/demo/visits/fam-010-a/start").json()
    assert client.post(f"/conversations/{conv['id']}/voice", content=b"nope").status_code == 422
    assert client.post(f"/conversations/{conv['id']}/voice", content=clip(31)).status_code == 422


def test_synthetic_voice_note_round_trip(voiced):
    client, speech, _ = voiced
    conv = client.post("/demo/visits/fam-010-a/start").json()
    conv = client.post(f"/conversations/{conv['id']}/voice/synthetic",
                       json={"text": "Montair कब लेनी है?"}).json()
    assert [c[0] for c in speech.calls] == ["synthesize", "transcribe"]
    assert conv["messages"][-1]["kind"] == "answer"


def test_visits_lists_approved_runs_and_starting_one_resumes_it(tmp_path):
    from voicerx import approve as approve_cli
    from test_followup_visits import draft_run
    folder = draft_run(tmp_path / "runs")
    approve_cli.main([str(folder), "--by", "Dr Lavanya Deshpande", "--review-date", "2026-10-26"])
    client = TestClient(create_app(tmp_path / "runs" / "followup-demo", runs_root=tmp_path / "runs", speech=None))
    visits = client.get("/visits").json()
    assert [(v["source"], v["case_id"]) for v in visits] == [
        ("demo", "fam-001-a"), ("demo", "fam-004-a"), ("demo", "fam-010-a"), ("run", "fam-010-a")]
    run = visits[-1]
    assert run["consent"] is True and run["review_date"] == "2026-10-26" and run["conversation_id"] is None
    conv = client.post(f"/visits/{run['visit_id']}/start").json()
    assert client.post(f"/visits/{run['visit_id']}/start").json()["id"] == conv["id"]
    assert client.get("/visits").json()[-1]["conversation_id"] == conv["id"]
    assert client.post(f"/visits/{run['visit_id']}/start?restart=true").json()["id"] != conv["id"]
    assert client.post("/visits/nope/start").status_code == 404



def test_web_start_can_ask_for_the_language_first(client):
    conv = client.post("/demo/visits/fam-001-a/start?ask_language=true").json()
    assert conv["messages"][0]["kind"] == "question" and conv["language_chosen"] is False
    conv = client.post(f"/conversations/{conv['id']}/messages", json={"button": "lang_en-IN"}).json()
    assert conv["language"] == "en-IN" and conv["messages"][-1]["kind"] == "summary"


def test_patient_memory_is_listed_locally_and_hidden_from_the_tunnel(client):
    conv = client.post("/demo/visits/fam-001-a/start").json()
    client.post(f"/conversations/{conv['id']}/messages", json={"text": "DOCTOR"})
    key = "sim-" + conv["patient_id"]
    memory = client.get(f"/patients/{key}/memory").json()
    assert "request" in [i["kind"] for i in memory["items"]] and memory["documents"] == []
    assert client.get(f"/patients/{key}/memory", headers={"cf-ray": "x"}).status_code == 403
    assert client.get("/patients/..%2Fescape/memory").status_code in (404, 422)



def test_web_upload_reads_a_report_for_the_doctor(tmp_path):
    from voicerx.contracts.documents import ReportReading
    reading = ReportReading(is_medical_report=True, report_type="X-ray report", report_date="2026-10-02",
                            transcription="", findings=[], medicines_named=[])
    client = TestClient(create_app(tmp_path, reader=lambda data, mime: (reading, "pdf_text", 1)))
    conv = client.post("/demo/visits/fam-004-a/start").json()
    done = client.post(f"/conversations/{conv['id']}/documents", content=b"%PDF-1.4 x",
                       headers={"Content-Type": "application/pdf"}).json()
    assert done["tasks"][-1]["kind"] == "document" and "X-ray report" in done["tasks"][-1]["note"]
    assert "X-ray report" not in done["messages"][-1]["text"]          # model-read text never goes to the patient
    assert client.post(f"/conversations/{conv['id']}/documents", content=b"x" * 10_000_001,
                       headers={"Content-Type": "application/pdf"}).status_code == 413
    memory = client.get(f"/patients/sim-{conv['patient_id']}/memory").json()
    assert memory["documents"][0]["reading"]["report_type"] == "X-ray report"
