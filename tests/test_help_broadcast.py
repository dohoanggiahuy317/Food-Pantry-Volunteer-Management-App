from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backends.memory_backend import MemoryBackend


ADMIN_ID = 101
LEAD_ID = 102
SECOND_LEAD_ID = 103
VOLUNTEER_ATTENDED_LOW_ID = 201
VOLUNTEER_ATTENDED_HIGH_ID = 202
VOLUNTEER_OTHER_HIGH_ID = 203
VOLUNTEER_OTHER_LOW_ID = 204


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _user(user_id: int, name: str, email: str, attendance_score: int = 100) -> dict:
    now = _iso_z(datetime.now(timezone.utc))
    return {
        "user_id": user_id,
        "full_name": name,
        "email": email,
        "phone_number": None,
        "timezone": "UTC",
        "attendance_score": attendance_score,
        "created_at": now,
        "updated_at": now,
        "auth_provider": "memory",
        "auth_uid": None,
    }


def _build_backend(tmp_path: Path) -> MemoryBackend:
    backend = MemoryBackend(data_path=tmp_path / "missing-seed.json")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    shift_start = now + timedelta(days=2)

    backend.store = {
        "users": [
            _user(ADMIN_ID, "Admin User", "admin@example.com"),
            _user(LEAD_ID, "Lead User", "lead@example.com"),
            _user(SECOND_LEAD_ID, "Second Lead", "second-lead@example.com"),
            _user(VOLUNTEER_ATTENDED_LOW_ID, "Attended Low", "attended-low@example.com", 70),
            _user(VOLUNTEER_ATTENDED_HIGH_ID, "Attended High", "attended-high@example.com", 95),
            _user(VOLUNTEER_OTHER_HIGH_ID, "Other High", "other-high@example.com", 100),
            _user(VOLUNTEER_OTHER_LOW_ID, "Other Low", "other-low@example.com", 60),
        ],
        "roles": [
            {"role_id": 1, "role_name": "ADMIN"},
            {"role_id": 2, "role_name": "PANTRY_LEAD"},
            {"role_id": 3, "role_name": "VOLUNTEER"},
        ],
        "user_roles": [
            {"user_id": ADMIN_ID, "role_id": 1},
            {"user_id": LEAD_ID, "role_id": 2},
            {"user_id": SECOND_LEAD_ID, "role_id": 2},
            {"user_id": VOLUNTEER_ATTENDED_LOW_ID, "role_id": 3},
            {"user_id": VOLUNTEER_ATTENDED_HIGH_ID, "role_id": 3},
            {"user_id": VOLUNTEER_OTHER_HIGH_ID, "role_id": 3},
            {"user_id": VOLUNTEER_OTHER_LOW_ID, "role_id": 3},
        ],
        "pantries": [
            {
                "pantry_id": 1,
                "name": "Test Pantry",
                "location_address": "123 Pantry St",
                "created_at": _iso_z(now),
                "updated_at": _iso_z(now),
            },
            {
                "pantry_id": 2,
                "name": "Other Pantry",
                "location_address": "456 Pantry St",
                "created_at": _iso_z(now),
                "updated_at": _iso_z(now),
            },
        ],
        "pantry_leads": [
            {"pantry_id": 1, "user_id": LEAD_ID},
            {"pantry_id": 1, "user_id": SECOND_LEAD_ID},
        ],
        "pantry_subscriptions": [],
        "shift_series": [],
        "shifts": [
            {
                "shift_id": 1,
                "pantry_id": 1,
                "shift_name": "Distribution",
                "start_time": _iso_z(shift_start),
                "end_time": _iso_z(shift_start + timedelta(hours=2)),
                "status": "OPEN",
                "created_by": LEAD_ID,
                "created_at": _iso_z(now),
                "updated_at": _iso_z(now),
                "shift_series_id": None,
                "series_position": None,
            },
            {
                "shift_id": 2,
                "pantry_id": 2,
                "shift_name": "Other Pantry Shift",
                "start_time": _iso_z(shift_start),
                "end_time": _iso_z(shift_start + timedelta(hours=2)),
                "status": "OPEN",
                "created_by": ADMIN_ID,
                "created_at": _iso_z(now),
                "updated_at": _iso_z(now),
                "shift_series_id": None,
                "series_position": None,
            },
        ],
        "shift_roles": [
            {"shift_role_id": 1, "shift_id": 1, "role_title": "Greeter", "required_count": 5, "filled_count": 0, "status": "OPEN"},
            {"shift_role_id": 2, "shift_id": 2, "role_title": "Sorter", "required_count": 5, "filled_count": 0, "status": "OPEN"},
        ],
        "shift_signups": [
            {"signup_id": 1, "shift_role_id": 1, "user_id": VOLUNTEER_ATTENDED_LOW_ID, "signup_status": "SHOW_UP", "reservation_expires_at": None, "created_at": _iso_z(now)},
            {"signup_id": 2, "shift_role_id": 1, "user_id": VOLUNTEER_ATTENDED_HIGH_ID, "signup_status": "SHOW_UP", "reservation_expires_at": None, "created_at": _iso_z(now)},
            {"signup_id": 3, "shift_role_id": 2, "user_id": VOLUNTEER_OTHER_HIGH_ID, "signup_status": "SHOW_UP", "reservation_expires_at": None, "created_at": _iso_z(now)},
        ],
        "help_broadcasts": [],
    }
    return backend


@pytest.fixture
def app_module(monkeypatch):
    monkeypatch.setenv("DATA_BACKEND", "memory")
    monkeypatch.setenv("AUTH_PROVIDER", "memory")
    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    yield module
    sys.modules.pop("app", None)


@pytest.fixture
def client_and_backend(app_module, monkeypatch, tmp_path):
    test_backend = _build_backend(tmp_path)
    monkeypatch.setattr(app_module, "backend", test_backend)
    monkeypatch.setattr(
        app_module,
        "send_shift_help_broadcast",
        lambda recipient, shift, pantry: {
            "ok": True,
            "code": "SHIFT_HELP_BROADCAST_SENT",
            "message": "sent",
            "recipient_email": recipient.get("email"),
            "subject": f"Help needed: {shift.get('shift_name')}",
            "provider": "test",
            "provider_response": None,
        },
    )
    app_module.app.config.update(TESTING=True)

    with app_module.app.test_client() as client:
        yield client, test_backend, app_module


def _login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user_id


def test_candidates_rank_prior_pantry_attendees_then_others(client_and_backend):
    client, _, _ = client_and_backend
    _login(client, LEAD_ID)

    response = client.get("/api/shifts/1/help-broadcast/candidates")
    assert response.status_code == 200
    payload = response.get_json()

    assert [row["user_id"] for row in payload] == [
        VOLUNTEER_ATTENDED_HIGH_ID,
        VOLUNTEER_ATTENDED_LOW_ID,
        VOLUNTEER_OTHER_HIGH_ID,
        VOLUNTEER_OTHER_LOW_ID,
    ]
    assert all(row["user_id"] not in {ADMIN_ID, LEAD_ID} for row in payload)
    assert payload[0]["has_attended_pantry"] is True
    assert payload[2]["has_attended_pantry"] is False


def test_candidates_search_filters_volunteers(client_and_backend):
    client, _, _ = client_and_backend
    _login(client, ADMIN_ID)

    response = client.get("/api/shifts/1/help-broadcast/candidates?q=other-high")
    assert response.status_code == 200
    payload = response.get_json()

    assert [row["user_id"] for row in payload] == [VOLUNTEER_OTHER_HIGH_ID]


def test_volunteer_cannot_list_or_send_broadcast(client_and_backend):
    client, _, _ = client_and_backend
    _login(client, VOLUNTEER_OTHER_LOW_ID)

    assert client.get("/api/shifts/1/help-broadcast/candidates").status_code == 403
    response = client.post(
        "/api/shifts/1/help-broadcast",
        json={"recipient_user_ids": [VOLUNTEER_OTHER_HIGH_ID]},
    )
    assert response.status_code == 403


def test_send_rejects_invalid_recipient_payloads(client_and_backend):
    client, _, _ = client_and_backend
    _login(client, LEAD_ID)

    empty_response = client.post("/api/shifts/1/help-broadcast", json={"recipient_user_ids": []})
    assert empty_response.status_code == 400

    too_many_response = client.post(
        "/api/shifts/1/help-broadcast",
        json={"recipient_user_ids": list(range(1, 27))},
    )
    assert too_many_response.status_code == 400

    non_volunteer_response = client.post(
        "/api/shifts/1/help-broadcast",
        json={"recipient_user_ids": [ADMIN_ID]},
    )
    assert non_volunteer_response.status_code == 400


def test_send_enforces_per_sender_cooldown(client_and_backend):
    client, backend, _ = client_and_backend
    _login(client, LEAD_ID)

    first_response = client.post(
        "/api/shifts/1/help-broadcast",
        json={"recipient_user_ids": [VOLUNTEER_OTHER_HIGH_ID]},
    )
    assert first_response.status_code == 200
    assert first_response.get_json()["sent_count"] == 1

    second_response = client.post(
        "/api/shifts/1/help-broadcast",
        json={"recipient_user_ids": [VOLUNTEER_OTHER_LOW_ID]},
    )
    assert second_response.status_code == 429
    assert second_response.get_json()["code"] == "HELP_BROADCAST_RATE_LIMITED"

    _login(client, SECOND_LEAD_ID)
    other_sender_response = client.post(
        "/api/shifts/1/help-broadcast",
        json={"recipient_user_ids": [VOLUNTEER_OTHER_LOW_ID]},
    )
    assert other_sender_response.status_code == 200
    assert len(backend.store["help_broadcasts"]) == 2


def test_unauthorized_lead_cannot_send_for_other_pantry(client_and_backend):
    client, _, _ = client_and_backend
    _login(client, LEAD_ID)

    response = client.post(
        "/api/shifts/2/help-broadcast",
        json={"recipient_user_ids": [VOLUNTEER_OTHER_LOW_ID]},
    )
    assert response.status_code == 403
