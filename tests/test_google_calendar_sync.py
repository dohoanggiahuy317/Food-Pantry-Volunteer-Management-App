from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backends.memory_backend import MemoryBackend


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@pytest.fixture
def app_module(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_BACKEND", "memory")
    monkeypatch.setenv("AUTH_PROVIDER", "memory")
    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    module.app.config["TESTING"] = True
    module.app.config["SECRET_KEY"] = "test-secret-key"
    module.backend = MemoryBackend(data_path=tmp_path / "missing-seed.json")
    yield module
    sys.modules.pop("app", None)


@pytest.fixture
def firebase_user(app_module):
    user = app_module.backend.create_user(
        full_name="Google User",
        email="google-user@example.com",
        phone_number="555-0100",
        roles=["VOLUNTEER"],
        timezone="UTC",
        auth_provider="firebase",
        auth_uid="firebase-user-1",
    )
    return user


@pytest.fixture
def authed_client(app_module, firebase_user):
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = int(firebase_user["user_id"])
    return client


def _add_signup_context(app_module, user_id: int) -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now + timedelta(days=2)
    backend = app_module.backend
    backend.store["pantries"] = [
        {
            "pantry_id": 1,
            "name": "Test Pantry",
            "location_address": "123 Pantry St",
            "created_at": _iso_z(now),
            "updated_at": _iso_z(now),
        }
    ]
    backend.store["shifts"] = [
        {
            "shift_id": 1,
            "pantry_id": 1,
            "shift_name": "Morning Shift",
            "start_time": _iso_z(start),
            "end_time": _iso_z(start + timedelta(hours=2)),
            "status": "OPEN",
            "created_by": user_id,
            "created_at": _iso_z(now),
            "updated_at": _iso_z(now),
            "shift_series_id": None,
            "series_position": None,
        }
    ]
    backend.store["shift_roles"] = [
        {
            "shift_role_id": 1,
            "shift_id": 1,
            "role_title": "Greeter",
            "required_count": 2,
            "filled_count": 1,
            "status": "OPEN",
        }
    ]
    backend.store["shift_signups"] = [
        {
            "signup_id": 1,
            "shift_role_id": 1,
            "user_id": user_id,
            "signup_status": "CONFIRMED",
            "reservation_expires_at": None,
            "created_at": _iso_z(now),
        }
    ]
    return 1


def test_google_calendar_status_unconfigured(app_module, authed_client, monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)

    response = authed_client.get("/api/google-calendar/status")

    assert response.status_code == 200
    assert response.get_json()["configured"] is False
    assert response.get_json()["connected"] is False


def test_google_calendar_status_configured_connected(app_module, authed_client, firebase_user, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    app_module.backend.upsert_google_calendar_connection(
        int(firebase_user["user_id"]),
        {
            "google_subject": "google-subject",
            "google_email": "google-user@example.com",
            "scopes_csv": "openid email https://www.googleapis.com/auth/calendar.events",
            "refresh_token": "refresh-token",
            "access_token": "access-token",
            "token_expires_at": _iso_z(datetime.now(timezone.utc) + timedelta(hours=1)),
        },
    )

    response = authed_client.get("/api/google-calendar/status")

    assert response.status_code == 200
    data = response.get_json()
    assert data["configured"] is True
    assert data["connected"] is True
    assert data["google_email"] == "google-user@example.com"


def test_google_calendar_connect_start_requires_firebase(app_module, authed_client, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    app_module.auth_service = SimpleNamespace(mode="memory")

    response = authed_client.post("/api/google-calendar/connect/start", json={})

    assert response.status_code == 400
    assert "Google/Firebase" in response.get_json()["error"]


def test_google_calendar_connect_start_returns_auth_url(app_module, authed_client, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    app_module.auth_service = SimpleNamespace(mode="firebase")

    response = authed_client.post("/api/google-calendar/connect/start", json={})

    assert response.status_code == 200
    assert "accounts.google.com" in response.get_json()["auth_url"]


def test_google_calendar_callback_rejects_invalid_state(app_module, authed_client):
    response = authed_client.get("/google-calendar/oauth/callback?state=bad-state&code=code")

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "ok: false" in body
    assert "authorization state was invalid" in body


def test_google_calendar_callback_stores_tokens_and_syncs_existing_signups(
    app_module,
    authed_client,
    firebase_user,
    monkeypatch,
):
    app_module.auth_service = SimpleNamespace(mode="firebase")
    signup_id = _add_signup_context(app_module, int(firebase_user["user_id"]))
    synced_signup_ids = []
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(
        app_module.google_calendar,
        "exchange_code_for_tokens",
        lambda code, default_redirect_uri: {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "scope": "openid email https://www.googleapis.com/auth/calendar.events",
        },
    )
    monkeypatch.setattr(
        app_module.google_calendar,
        "fetch_user_info",
        lambda access_token: {"sub": "google-subject", "email": "google-user@example.com"},
    )
    monkeypatch.setattr(app_module, "sync_signup_update_to_google_calendar", lambda value: synced_signup_ids.append(value))
    with authed_client.session_transaction() as sess:
        sess["google_calendar_oauth_state"] = "expected-state"
        sess["google_calendar_oauth_user_id"] = int(firebase_user["user_id"])

    response = authed_client.get("/google-calendar/oauth/callback?state=expected-state&code=oauth-code")

    assert response.status_code == 200
    assert "ok: true" in response.get_data(as_text=True)
    connection = app_module.backend.get_google_calendar_connection(int(firebase_user["user_id"]))
    assert connection["refresh_token"] == "refresh-token"
    assert connection["google_email"] == "google-user@example.com"
    assert synced_signup_ids == [signup_id]


def test_sync_signup_create_does_not_call_google_without_connection(app_module, firebase_user, monkeypatch):
    signup_id = _add_signup_context(app_module, int(firebase_user["user_id"]))
    calls = []
    monkeypatch.setattr(app_module.google_calendar, "http_json", lambda *args, **kwargs: calls.append((args, kwargs)))

    app_module.sync_signup_create_to_google_calendar(signup_id)

    assert calls == []


def test_sync_signup_create_calls_google_when_connected(app_module, firebase_user, monkeypatch):
    signup_id = _add_signup_context(app_module, int(firebase_user["user_id"]))
    app_module.backend.upsert_google_calendar_connection(
        int(firebase_user["user_id"]),
        {
            "google_subject": "google-subject",
            "google_email": "google-user@example.com",
            "scopes_csv": "openid email https://www.googleapis.com/auth/calendar.events",
            "refresh_token": "refresh-token",
            "access_token": "access-token",
            "token_expires_at": _iso_z(datetime.now(timezone.utc) + timedelta(hours=1)),
        },
    )
    calls = []

    def fake_http_json(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return {"id": "google-event-1"}

    monkeypatch.setattr(app_module.google_calendar, "http_json", fake_http_json)

    app_module.sync_signup_create_to_google_calendar(signup_id)

    assert calls[0][0] == "POST"
    assert app_module.backend.get_google_calendar_event_link(signup_id)["google_event_id"] == "google-event-1"
