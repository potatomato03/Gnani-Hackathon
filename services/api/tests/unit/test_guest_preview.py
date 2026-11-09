"""The guest preview is read-only (runbook D-146)."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from voicerx.app import auth, main


def session(user=auth.GUEST_USER, org=auth.GUEST_ORG):
    return {'user_id': user, 'organisation_id': org, 'csrf_token': 'csrf', 'display_name': 'Dr Guest',
            'registration_no': None, 'specialty': 'general_medicine', 'synthetic': True, 'role': 'doctor',
            'organisation_name': 'ARDAI Guest Clinic', 'timezone': 'Asia/Kolkata',
            'expires_at': datetime(2026, 11, 10, tzinfo=timezone.utc)}


def request(method, path, who):
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path), cookies={auth.COOKIE: 'token'},
                           headers={'X-CSRF-Token': 'csrf'}, state=SimpleNamespace(auth_session=who))


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setitem(main.state, 'settings', SimpleNamespace(allowed_origins=[]))


def test_a_guest_can_read_but_not_change_anything():
    guest = session()
    assert main.session_of(request('GET', '/api/v1/patients', guest)) is guest
    for method, path in (('POST', '/api/v1/encounters/enc-1/approvals'), ('POST', '/api/v1/patients/p/encounters'),
                         ('PUT', '/api/v1/live-recordings/l/parts/0'), ('POST', '/api/v1/encounters/e/followup/messages'),
                         ('POST', '/api/v1/patients'), ('POST', '/api/v1/pharmacy/stock')):
        with pytest.raises(auth.Forbidden, match='read-only guest preview'):
            main.session_of(request(method, path, guest))


def test_a_guest_may_sign_out_and_look_up_drug_labels():
    for path in ('/api/v1/auth/logout', '/api/v1/knowledge/search'):
        assert main.session_of(request('POST', path, session())) is not None


def test_other_doctors_are_not_affected():
    doctor = session(user='doctor-1', org='clinic-1')
    assert main.session_of(request('POST', '/api/v1/encounters/enc-1/approvals', doctor)) is doctor
    # The guest user in another clinic is not the guest preview.
    assert not auth.is_guest(session(org='clinic-1'))


def test_the_app_learns_it_is_a_guest_session():
    assert auth.session_view(session())['guest'] is True
    assert auth.session_view(session(user='doctor-1', org='clinic-1'))['guest'] is False
