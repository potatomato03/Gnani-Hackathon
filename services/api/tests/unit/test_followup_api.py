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
