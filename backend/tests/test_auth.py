from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class FakeFirebaseAuthService:
    mode = "firebase"

    def __init__(self, email: str, firebase_uid: str, display_name: str = "Test User") -> None:
        self.email = email
        self.firebase_uid = firebase_uid
        self.display_name = display_name

    def get_client_config(self) -> dict[str, object]:
        return {
            "provider": "firebase",
            "firebase": {
                "apiKey": "test-api-key",
                "authDomain": "test.firebaseapp.com",
                "projectId": "test-project",
                "appId": "test-app-id",
            },
        }

    def verify_google_token(self, id_token: str) -> object:
        assert id_token == "fake-token"
        return type(
            "IdentityPayload",
            (),
            {
                "provider": "firebase",
                "provider_user_id": self.firebase_uid,
                "email": self.email,
                "email_verified": True,
                "display_name": self.display_name,
            },
        )()

    def list_memory_accounts(self) -> list[dict[str, object]]:
        return []

    def resolve_memory_account(self, sample_account_id: str) -> dict[str, object]:
        raise AssertionError("resolve_memory_account should not be used in firebase tests")


def load_app_module(auth_provider: str = "memory"):
    os.environ["DATA_BACKEND"] = "memory"
    os.environ["AUTH_PROVIDER"] = auth_provider
    os.environ["FLASK_SECRET_KEY"] = "test-secret"

    if "app" in sys.modules:
        return importlib.reload(sys.modules["app"])

    return importlib.import_module("app")


def test_unauthenticated_routes_require_session_except_public_routes():
    app_module = load_app_module("memory")
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        me_response = client.get("/api/me")
        protected_response = client.get("/api/pantries")
        public_response = client.get("/api/public/pantries")

    assert me_response.status_code == 401
    assert protected_response.status_code == 401
    assert public_response.status_code == 200


def test_memory_login_and_logout_flow():
    app_module = load_app_module("memory")
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        config_response = client.get("/api/auth/config")
        assert config_response.status_code == 200
        assert config_response.get_json()["provider"] == "memory"

        login_response = client.post(
            "/api/auth/login/memory",
            json={"sample_account_id": "volunteer"},
        )
        assert login_response.status_code == 200
        assert login_response.get_json()["next"] == "app"

        me_response = client.get("/api/me")
        assert me_response.status_code == 200
        assert "VOLUNTEER" in me_response.get_json()["roles"]

        logout_response = client.post("/api/auth/logout")
        assert logout_response.status_code == 200
        assert logout_response.get_json() == {"ok": True}

        me_after_logout = client.get("/api/me")
        assert me_after_logout.status_code == 401


def test_google_login_unknown_user_requires_signup_then_creates_volunteer():
    app_module = load_app_module("memory")
    app_module.app.config["TESTING"] = True
    app_module.auth_service = FakeFirebaseAuthService(
        email="new.volunteer@example.org",
        firebase_uid="firebase-user-1",
        display_name="New Volunteer",
    )

    with app_module.app.test_client() as client:
        login_response = client.post("/api/auth/login/google", json={"id_token": "fake-token"})
        assert login_response.status_code == 200
        assert login_response.get_json()["signup_required"] is True

        signup_response = client.post(
            "/api/auth/signup/google",
            json={
                "id_token": "fake-token",
                "full_name": "New Volunteer",
                "phone_number": "555-0101",
            },
        )
        assert signup_response.status_code == 201
        created_user = signup_response.get_json()["user"]
        assert created_user["email"] == "new.volunteer@example.org"
        assert "VOLUNTEER" in created_user["roles"]

        backend_user = app_module.backend.get_user_by_email("new.volunteer@example.org")
        assert backend_user is not None
        assert backend_user["firebase_uid"] == "firebase-user-1"


def test_google_login_links_existing_local_user_by_email():
    app_module = load_app_module("memory")
    app_module.app.config["TESTING"] = True
    app_module.auth_service = FakeFirebaseAuthService(
        email="super@example.org",
        firebase_uid="firebase-admin-1",
        display_name="Admin User",
    )

    with app_module.app.test_client() as client:
        login_response = client.post("/api/auth/login/google", json={"id_token": "fake-token"})
        assert login_response.status_code == 200
        payload = login_response.get_json()
        assert payload["next"] == "app"
        assert payload["linked_existing_user"] is True
        assert "ADMIN" in payload["user"]["roles"]

    linked_user = app_module.backend.get_user_by_email("super@example.org")
    assert linked_user is not None
    assert linked_user["firebase_uid"] == "firebase-admin-1"
