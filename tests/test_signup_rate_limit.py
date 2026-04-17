from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backends.memory_backend import MemoryBackend

VOLUNTEER_USER_ID = 101


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_test_backend(tmp_path: Path) -> MemoryBackend:
    backend = MemoryBackend(data_path=tmp_path / "missing-seed.json")
    now = datetime.now(timezone.utc).replace(microsecond=0)

    backend.store = {
        "users": [
            {
                "user_id": VOLUNTEER_USER_ID,
                "full_name": "Test Volunteer",
                "email": "volunteer@example.com",
                "phone_number": None,
                "timezone": None,
                "attendance_score": 100,
                "created_at": _iso_z(now),
                "updated_at": _iso_z(now),
                "auth_provider": "memory",
                "auth_uid": None,
            }
        ],
        "roles": [
            {"role_id": 3, "role_name": "VOLUNTEER"},
        ],
        "user_roles": [
            {"user_id": VOLUNTEER_USER_ID, "role_id": 3},
        ],
        "pantries": [
            {
                "pantry_id": 1,
                "name": "Test Pantry",
                "location_address": "123 Test St",
                "created_at": _iso_z(now),
                "updated_at": _iso_z(now),
            }
        ],
        "pantry_leads": [],
        "pantry_subscriptions": [],
        "shift_series": [],
        "shifts": [],
        "shift_roles": [],
        "shift_signups": [],
    }

    for shift_id in range(1, 7):
        start_time = now + timedelta(days=shift_id)
        end_time = start_time + timedelta(hours=2)
        backend.store["shifts"].append(
            {
                "shift_id": shift_id,
                "pantry_id": 1,
                "shift_name": f"Shift {shift_id}",
                "start_time": _iso_z(start_time),
                "end_time": _iso_z(end_time),
                "status": "OPEN",
                "created_by": 1,
                "created_at": _iso_z(now),
                "updated_at": _iso_z(now),
                "shift_series_id": None,
                "series_position": None,
            }
        )
        backend.store["shift_roles"].append(
            {
                "shift_role_id": shift_id,
                "shift_id": shift_id,
                "role_title": f"Role {shift_id}",
                "required_count": 10,
                "filled_count": 0,
                "status": "OPEN",
                "created_at": _iso_z(now),
            }
        )

    backend.next_shift_id = 7
    backend.next_shift_role_id = 7
    backend.next_signup_id = 1
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
    test_backend = _build_test_backend(tmp_path)
    monkeypatch.setattr(app_module, "backend", test_backend)
    monkeypatch.setattr(app_module, "send_signup_confirmation_if_configured", lambda *args, **kwargs: None)
    app_module.app.config.update(TESTING=True)

    with app_module.app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = VOLUNTEER_USER_ID
        yield client, test_backend, app_module


def _create_signup(client, shift_role_id: int):
    return client.post(f"/api/shift-roles/{shift_role_id}/signup", json={})


def _rewrite_signup_created_at_rows(backend: MemoryBackend, created_at_values: list[datetime]) -> None:
    assert len(backend.store["shift_signups"]) == len(created_at_values)
    for signup, created_at in zip(backend.store["shift_signups"], created_at_values):
        signup["created_at"] = _iso_z(created_at.replace(microsecond=0))


def test_blocks_sixth_signup_within_24_hours(client_and_backend):
    client, backend, app_module = client_and_backend

    for shift_role_id in range(1, 6):
        response = _create_signup(client, shift_role_id)
        assert response.status_code == 201

    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_at_values = [
        now - timedelta(hours=23, minutes=55),
        now - timedelta(hours=22),
        now - timedelta(hours=18),
        now - timedelta(hours=12),
        now - timedelta(hours=1),
    ]
    _rewrite_signup_created_at_rows(backend, created_at_values)

    response = _create_signup(client, 6)

    assert response.status_code == 429
    payload = response.get_json()
    assert payload["code"] == "SIGNUP_RATE_LIMITED"
    assert payload["error"] == "You can sign up for at most 5 shifts within 24 hours"
    assert payload["cooldown_ends_at"] == _iso_z(created_at_values[0] + app_module.SIGNUP_RATE_LIMIT_WINDOW)


def test_allows_signup_after_cooldown_expires(client_and_backend):
    client, backend, _ = client_and_backend

    for shift_role_id in range(1, 6):
        response = _create_signup(client, shift_role_id)
        assert response.status_code == 201

    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_at_values = [
        now - timedelta(hours=24, minutes=1),
        now - timedelta(hours=20),
        now - timedelta(hours=12),
        now - timedelta(hours=6),
        now - timedelta(hours=1),
    ]
    _rewrite_signup_created_at_rows(backend, created_at_values)

    response = _create_signup(client, 6)

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["shift_role_id"] == 6
    assert payload["user"]["user_id"] == VOLUNTEER_USER_ID
