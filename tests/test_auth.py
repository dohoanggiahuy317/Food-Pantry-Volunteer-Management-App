import sys
from pathlib import Path

# Add backend directory to Python path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

import pytest
from auth import AuthError


class TestAuthService:
    """Test authentication service functionality."""

    def test_auth_service_creation(self, auth_service):
        """Test that auth service can be created."""
        assert auth_service is not None
        assert hasattr(auth_service, "mode")

    def test_list_memory_accounts(self, auth_service):
        """Test listing memory accounts."""
        accounts = auth_service.list_memory_accounts()
        assert isinstance(accounts, list)

    def test_resolve_memory_account(self, auth_service):
        """Test resolving memory account."""
        accounts = auth_service.list_memory_accounts()
        if accounts:
            account = auth_service.resolve_memory_account(accounts[0]["id"])
            assert isinstance(account, dict)
            assert "email" in account
        else:
            # If no accounts, this should raise an error
            with pytest.raises((AuthError, ValueError, KeyError)):
                auth_service.resolve_memory_account("nonexistent")

    def test_get_client_config_includes_memory_accounts(self, auth_service):
        """Test client auth config exposes memory account choices."""
        config = auth_service.get_client_config()

        assert config["provider"] == auth_service.mode
        assert config["memory_accounts"] == auth_service.list_memory_accounts()
        assert config["memory_accounts"] is not auth_service.list_memory_accounts()

    def test_resolve_unknown_memory_account_raises_auth_error(self, auth_service):
        """Test resolving an unknown memory account returns the expected auth error."""
        with pytest.raises(AuthError) as exc_info:
            auth_service.resolve_memory_account("missing-account")

        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "MEMORY_ACCOUNT_NOT_FOUND"

    def test_delete_user_memory_mode_is_noop(self, auth_service):
        """Test memory auth delete hook is intentionally a no-op."""
        assert auth_service.delete_user("any-uid") is None


class TestAuthError:
    """Test AuthError exception."""

    def test_auth_error_creation(self):
        """Test creating AuthError."""
        error = AuthError("Test message")
        assert str(error) == "Test message"
        assert error.message == "Test message"
        assert error.status_code == 400
        assert error.code is None

    def test_auth_error_with_code(self):
        """Test AuthError with status code and error code."""
        error = AuthError("Test message", 403, "FORBIDDEN")
        assert error.status_code == 403
        assert error.code == "FORBIDDEN"


class TestMemoryAuth:
    """Test memory authentication."""

    def test_verify_google_token_memory_mode(self, auth_service):
        """Test Google token verification in memory mode."""
        if auth_service.mode == "memory":
            # Memory mode might not support Google tokens
            with pytest.raises((AuthError, NotImplementedError)):
                auth_service.verify_google_token("fake_token")
