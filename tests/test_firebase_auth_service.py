from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def reset_firebase_auth_service_module():
    sys.modules.pop("auth.firebase_auth_service", None)
    yield
    sys.modules.pop("auth.firebase_auth_service", None)


def _stub_firebase_modules():
    firebase_admin = types.ModuleType("firebase_admin")
    firebase_admin._apps = []
    firebase_admin.initialize_app = MagicMock()

    firebase_auth = types.ModuleType("firebase_admin.auth")

    credentials = types.ModuleType("firebase_admin.credentials")
    credentials.Certificate = MagicMock(side_effect=lambda payload: {"payload": payload})

    firebase_admin.auth = firebase_auth
    firebase_admin.credentials = credentials
    return firebase_admin, firebase_auth, credentials


def _import_service_module():
    return importlib.import_module("auth.firebase_auth_service")


def _set_required_firebase_env(monkeypatch, credentials_value: str) -> None:
    monkeypatch.setenv("FIREBASE_API_KEY", "api-key")
    monkeypatch.setenv("FIREBASE_AUTH_DOMAIN", "project.firebaseapp.com")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "project-id")
    monkeypatch.setenv("FIREBASE_APP_ID", "app-id")
    monkeypatch.setenv("FIREBASE_ADMIN_CREDENTIALS", credentials_value)


def test_accepts_inline_json_credentials(monkeypatch):
    _set_required_firebase_env(monkeypatch, '{"type":"service_account","project_id":"demo-project"}')
    firebase_admin, firebase_auth, credentials = _stub_firebase_modules()

    with pytest.MonkeyPatch.context() as patch_ctx:
        patch_ctx.setitem(sys.modules, "firebase_admin", firebase_admin)
        patch_ctx.setitem(sys.modules, "firebase_admin.auth", firebase_auth)
        patch_ctx.setitem(sys.modules, "firebase_admin.credentials", credentials)
        module = _import_service_module()
        module.FirebaseAuthService()

    assert credentials.Certificate.call_args.args[0] == {
        "type": "service_account",
        "project_id": "demo-project",
    }
    firebase_admin.initialize_app.assert_called_once()


def test_accepts_file_path_credentials(monkeypatch, tmp_path: Path):
    credential_path = tmp_path / "firebase-admin.json"
    credential_path.write_text('{"type":"service_account"}', encoding="utf-8")
    _set_required_firebase_env(monkeypatch, str(credential_path))
    firebase_admin, firebase_auth, credentials = _stub_firebase_modules()

    with pytest.MonkeyPatch.context() as patch_ctx:
        patch_ctx.setitem(sys.modules, "firebase_admin", firebase_admin)
        patch_ctx.setitem(sys.modules, "firebase_admin.auth", firebase_auth)
        patch_ctx.setitem(sys.modules, "firebase_admin.credentials", credentials)
        module = _import_service_module()
        module.FirebaseAuthService()

    assert credentials.Certificate.call_args.args[0] == str(credential_path)
    firebase_admin.initialize_app.assert_called_once()


def test_rejects_missing_credentials_file(monkeypatch):
    _set_required_firebase_env(monkeypatch, "missing-service-account.json")
    firebase_admin, firebase_auth, credentials = _stub_firebase_modules()

    with pytest.MonkeyPatch.context() as patch_ctx:
        patch_ctx.setitem(sys.modules, "firebase_admin", firebase_admin)
        patch_ctx.setitem(sys.modules, "firebase_admin.auth", firebase_auth)
        patch_ctx.setitem(sys.modules, "firebase_admin.credentials", credentials)
        module = _import_service_module()
        with pytest.raises(RuntimeError, match="JSON document or a readable file path"):
            module.FirebaseAuthService()
