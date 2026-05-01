"""
Auth Component Tests

Tests FirebaseAuthService in isolation. The only external dependency —
firebase_admin.auth.verify_id_token — is replaced by the mock_firebase_verify
fixture. No MySQL is required; the auth service has no DB dependency.

Run with: pytest tests/component/test_auth_component.py -v -m component
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.component


# ── Service factory (fresh instance per test) ─────────────────────────────────

def _make_service(mock_firebase_verify):
    """
    Instantiate FirebaseAuthService under the mock fixture's active patches.
    The fixture already fakes firebase_admin._apps (skips SDK init) and patches
    firebase_admin.auth.verify_id_token. The service's __init__ needs all four
    FIREBASE_* env vars to be non-empty — .env.test supplies dummy values.
    """
    from auth.firebase_auth_service import FirebaseAuthService
    return FirebaseAuthService()


# ── Token Verification ────────────────────────────────────────────────────────

class TestVerifyGoogleToken:
    def test_valid_token_returns_identity_payload(self, mock_firebase_verify):
        service = _make_service(mock_firebase_verify)
        result = service.verify_google_token("valid-test-token")

        assert result.provider == "firebase"
        assert result.uid == "test-firebase-uid-123"
        assert result.email == "volunteer@example.com"
        assert result.email_verified is True
        assert result.display_name == "Test Volunteer"

    def test_verify_id_token_called_with_provided_token(self, mock_firebase_verify):
        service = _make_service(mock_firebase_verify)
        service.verify_google_token("my-specific-token")
        mock_firebase_verify.assert_called_once_with("my-specific-token")

    def test_email_is_lowercased_in_payload(self, mock_firebase_verify):
        mock_firebase_verify.return_value = {
            "uid": "uid-001",
            "email": "UPPER@EXAMPLE.COM",
            "email_verified": True,
            "name": "User",
        }
        service = _make_service(mock_firebase_verify)
        result = service.verify_google_token("token")
        assert result.email == "upper@example.com"

    def test_display_name_none_when_not_in_token(self, mock_firebase_verify):
        mock_firebase_verify.return_value = {
            "uid": "uid-no-name",
            "email": "noname@example.com",
            "email_verified": True,
        }
        service = _make_service(mock_firebase_verify)
        result = service.verify_google_token("token")
        assert result.display_name is None

    # ── Error Cases ────────────────────────────────────────────────────────────

    def test_empty_token_raises_400(self, mock_firebase_verify):
        from auth.base import AuthError
        service = _make_service(mock_firebase_verify)
        with pytest.raises(AuthError) as exc_info:
            service.verify_google_token("")
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "MISSING_ID_TOKEN"
        mock_firebase_verify.assert_not_called()

    def test_whitespace_only_token_raises_400(self, mock_firebase_verify):
        from auth.base import AuthError
        service = _make_service(mock_firebase_verify)
        with pytest.raises(AuthError) as exc_info:
            service.verify_google_token("   ")
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "MISSING_ID_TOKEN"

    def test_invalid_token_raises_401(self, mock_firebase_verify):
        from auth.base import AuthError
        mock_firebase_verify.side_effect = Exception("Token has expired")
        service = _make_service(mock_firebase_verify)
        with pytest.raises(AuthError) as exc_info:
            service.verify_google_token("expired-token")
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "INVALID_ID_TOKEN"

    def test_unverified_email_raises_403(self, mock_firebase_verify):
        from auth.base import AuthError
        mock_firebase_verify.return_value = {
            "uid": "uid-unverified",
            "email": "unverified@example.com",
            "email_verified": False,
            "name": "Unverified User",
        }
        service = _make_service(mock_firebase_verify)
        with pytest.raises(AuthError) as exc_info:
            service.verify_google_token("token")
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "EMAIL_NOT_VERIFIED"

    def test_missing_uid_in_token_raises_400(self, mock_firebase_verify):
        from auth.base import AuthError
        mock_firebase_verify.return_value = {
            "uid": "",
            "email": "valid@example.com",
            "email_verified": True,
        }
        service = _make_service(mock_firebase_verify)
        with pytest.raises(AuthError) as exc_info:
            service.verify_google_token("token")
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "INVALID_IDENTITY"

    def test_missing_email_in_token_raises_400(self, mock_firebase_verify):
        from auth.base import AuthError
        mock_firebase_verify.return_value = {
            "uid": "uid-no-email",
            "email": "",
            "email_verified": True,
        }
        service = _make_service(mock_firebase_verify)
        with pytest.raises(AuthError) as exc_info:
            service.verify_google_token("token")
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "INVALID_IDENTITY"


# ── Client Config ─────────────────────────────────────────────────────────────

class TestClientConfig:
    def test_get_client_config_returns_expected_structure(self, mock_firebase_verify):
        service = _make_service(mock_firebase_verify)
        config = service.get_client_config()
        assert config["provider"] == "firebase"
        assert "firebase" in config
        firebase = config["firebase"]
        assert "apiKey" in firebase
        assert "authDomain" in firebase
        assert "projectId" in firebase
        assert "appId" in firebase

    def test_get_client_config_uses_dummy_env_values(self, mock_firebase_verify):
        service = _make_service(mock_firebase_verify)
        config = service.get_client_config()
        assert config["firebase"]["apiKey"] == "test-api-key"
        assert config["firebase"]["projectId"] == "test-project"

    def test_get_client_config_does_not_expose_admin_credentials(self, mock_firebase_verify):
        service = _make_service(mock_firebase_verify)
        config = service.get_client_config()
        config_str = str(config)
        assert "service_account" not in config_str
        assert "private_key" not in config_str


# ── Memory Auth Methods (disabled in firebase mode) ───────────────────────────

class TestMemoryAuthDisabled:
    def test_list_memory_accounts_returns_empty_list(self, mock_firebase_verify):
        service = _make_service(mock_firebase_verify)
        assert service.list_memory_accounts() == []

    def test_resolve_memory_account_raises_auth_error(self, mock_firebase_verify):
        from auth.base import AuthError
        service = _make_service(mock_firebase_verify)
        with pytest.raises(AuthError) as exc_info:
            service.resolve_memory_account("any-account-id")
        assert exc_info.value.code == "MEMORY_AUTH_DISABLED"


# ── Delete User ───────────────────────────────────────────────────────────────

class TestDeleteUser:
    def test_delete_user_calls_firebase_delete_with_uid(self, mock_firebase_verify):
        fake_apps = {"[DEFAULT]": MagicMock()}
        with patch("firebase_admin._apps", fake_apps), \
             patch("firebase_admin.auth.verify_id_token"), \
             patch("firebase_admin.auth.delete_user") as mock_delete:
            from auth.firebase_auth_service import FirebaseAuthService
            service = FirebaseAuthService()
            service.delete_user("uid-to-delete")
            mock_delete.assert_called_once_with("uid-to-delete")

    def test_delete_user_empty_uid_raises_400(self, mock_firebase_verify):
        from auth.base import AuthError
        service = _make_service(mock_firebase_verify)
        with pytest.raises(AuthError) as exc_info:
            service.delete_user("")
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "MISSING_UID"

    def test_delete_user_firebase_failure_raises_502(self, mock_firebase_verify):
        from auth.base import AuthError
        fake_apps = {"[DEFAULT]": MagicMock()}
        with patch("firebase_admin._apps", fake_apps), \
             patch("firebase_admin.auth.verify_id_token"), \
             patch("firebase_admin.auth.delete_user", side_effect=Exception("Firebase down")):
            from auth.firebase_auth_service import FirebaseAuthService
            service = FirebaseAuthService()
            with pytest.raises(AuthError) as exc_info:
                service.delete_user("some-uid")
            assert exc_info.value.status_code == 502
            assert exc_info.value.code == "FIREBASE_DELETE_FAILED"
