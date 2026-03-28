from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DATA_BACKEND", "memory")
os.environ.setdefault("AUTH_PROVIDER", "memory")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")

if "flask_cors" not in sys.modules:
    flask_cors_stub = types.ModuleType("flask_cors")

    def _cors_stub(app, *args, **kwargs):  # type: ignore[no-untyped-def]
        return app

    flask_cors_stub.CORS = _cors_stub
    sys.modules["flask_cors"] = flask_cors_stub

import app as app_module
from auth.base import AuthError, IdentityPayload
from backends.memory_backend import MemoryBackend


class DummyMemoryAuthService:
    mode = "memory"

    def get_client_config(self) -> dict[str, object]:
        return {"provider": "memory", "memory_accounts": []}

    def verify_google_token(self, id_token: str) -> IdentityPayload:
        raise AuthError("Google sign-in is unavailable in memory auth mode", 400, "GOOGLE_AUTH_DISABLED")

    def list_memory_accounts(self) -> list[dict[str, object]]:
        return []

    def resolve_memory_account(self, sample_account_id: str) -> dict[str, object]:
        raise AuthError("Unknown sample account", 404, "MEMORY_ACCOUNT_NOT_FOUND")

    def delete_user(self, uid: str) -> None:
        return None


class DummyFirebaseAuthService:
    mode = "firebase"

    def __init__(self, identity: IdentityPayload) -> None:
        self.identity = identity
        self.deleted_uids: list[str] = []

    def get_client_config(self) -> dict[str, object]:
        return {"provider": "firebase", "firebase": {}}

    def verify_google_token(self, id_token: str) -> IdentityPayload:
        return self.identity

    def list_memory_accounts(self) -> list[dict[str, object]]:
        return []

    def resolve_memory_account(self, sample_account_id: str) -> dict[str, object]:
        raise AuthError("Memory login is unavailable in firebase auth mode", 400, "MEMORY_AUTH_DISABLED")

    def delete_user(self, uid: str) -> None:
        self.deleted_uids.append(uid)


class AccountFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        app_module.app.config["TESTING"] = True
        app_module.backend = MemoryBackend()
        app_module.auth_service = DummyMemoryAuthService()
        self.client = app_module.app.test_client()

    def login_session_as(self, user_id: int) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = user_id

    def test_patch_me_requires_authentication(self) -> None:
        response = self.client.patch("/api/me", json={"full_name": "Updated Name"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "No user")

    def test_patch_me_updates_basic_fields(self) -> None:
        self.login_session_as(6)

        response = self.client.patch(
            "/api/me",
            json={"full_name": "Ben Updated", "phone_number": "555-111-2222"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["full_name"], "Ben Updated")
        self.assertEqual(payload["phone_number"], "555-111-2222")

        stored = app_module.backend.get_user_by_id(6)
        self.assertEqual(stored["full_name"], "Ben Updated")
        self.assertEqual(stored["phone_number"], "555-111-2222")

    def test_google_login_links_legacy_user_by_email_to_firebase_uid(self) -> None:
        app_module.auth_service = DummyFirebaseAuthService(
            IdentityPayload(
                provider="firebase",
                uid="firebase-uid-ben",
                email="ben@volunteer.org",
                email_verified=True,
                display_name="Ben Turner",
            )
        )

        response = self.client.post("/api/auth/login/google", json={"id_token": "token"})

        self.assertEqual(response.status_code, 200)
        linked_user = app_module.backend.get_user_by_id(6)
        self.assertEqual(linked_user["auth_provider"], "firebase")
        self.assertEqual(linked_user["auth_uid"], "firebase-uid-ben")

    def test_google_login_uses_auth_uid_and_syncs_changed_email(self) -> None:
        app_module.backend.update_user(6, {"auth_provider": "firebase", "auth_uid": "firebase-uid-ben"})
        app_module.backend.update_user(6, {"email": "ben.old@volunteer.org"})
        app_module.auth_service = DummyFirebaseAuthService(
            IdentityPayload(
                provider="firebase",
                uid="firebase-uid-ben",
                email="ben.new@volunteer.org",
                email_verified=True,
                display_name="Ben Turner",
            )
        )

        response = self.client.post("/api/auth/login/google", json={"id_token": "token"})

        self.assertEqual(response.status_code, 200)
        synced_user = app_module.backend.get_user_by_id(6)
        self.assertEqual(synced_user["email"], "ben.new@volunteer.org")
        self.assertEqual(synced_user["auth_uid"], "firebase-uid-ben")

    def test_google_login_rejects_email_conflict_for_linked_user(self) -> None:
        app_module.backend.update_user(6, {"auth_provider": "firebase", "auth_uid": "firebase-uid-ben"})
        app_module.backend.update_user(6, {"email": "ben.old@volunteer.org"})
        app_module.auth_service = DummyFirebaseAuthService(
            IdentityPayload(
                provider="firebase",
                uid="firebase-uid-ben",
                email="chloe@volunteer.org",
                email_verified=True,
                display_name="Ben Turner",
            )
        )

        response = self.client.post("/api/auth/login/google", json={"id_token": "token"})

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertEqual(payload["code"], "AUTH_EMAIL_CONFLICT")
        self.assertEqual(app_module.backend.get_user_by_id(6)["email"], "ben.old@volunteer.org")

    def test_prepare_email_change_rejects_local_conflict(self) -> None:
        firebase_auth = DummyFirebaseAuthService(
            IdentityPayload(
                provider="firebase",
                uid="firebase-uid-ben",
                email="ben@volunteer.org",
                email_verified=True,
                display_name="Ben Turner",
            )
        )
        app_module.auth_service = firebase_auth
        app_module.backend.update_user(6, {"auth_provider": "firebase", "auth_uid": "firebase-uid-ben"})
        self.login_session_as(6)

        response = self.client.post("/api/me/email-change/prepare", json={"new_email": "chloe@volunteer.org"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "That email is already associated with another account")

    def test_delete_me_removes_local_user_and_deletes_firebase_account(self) -> None:
        firebase_auth = DummyFirebaseAuthService(
            IdentityPayload(
                provider="firebase",
                uid="firebase-uid-ben",
                email="ben@volunteer.org",
                email_verified=True,
                display_name="Ben Turner",
            )
        )
        app_module.auth_service = firebase_auth
        app_module.backend.update_user(6, {"auth_provider": "firebase", "auth_uid": "firebase-uid-ben"})
        self.login_session_as(6)

        response = self.client.delete("/api/me", json={"id_token": "token"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})
        self.assertEqual(firebase_auth.deleted_uids, ["firebase-uid-ben"])
        self.assertIsNone(app_module.backend.get_user_by_id(6))


if __name__ == "__main__":
    unittest.main()
