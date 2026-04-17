import sys
from pathlib import Path

# Add backend directory to Python path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

import pytest


class TestApp:
    """Test the main Flask application."""

    def test_app_creation(self, setup_backend):
        """Test that the app can be created."""
        app_module, _ = setup_backend
        assert app_module.app is not None
        assert app_module.app.name == "app"

    def test_app_config(self, test_app):
        """Test app configuration."""
        assert test_app.config["TESTING"] is True
        assert test_app.config["SECRET_KEY"] == "test-secret-key"


class TestAuthRoutes:
    """Test authentication-related routes."""

    def test_protected_route_unauthenticated(self, client):
        """Test that protected routes require authentication."""
        response = client.get("/api/users")
        assert response.status_code == 401
        data = response.get_json()
        assert "error" in data
        assert "Authentication required" in data["error"]


class TestUserRoutes:
    """Test user-related routes."""

    def test_list_users_unauthenticated(self, client):
        """Test that listing users requires authentication."""
        response = client.get("/api/users")
        assert response.status_code == 401

    def test_create_user_unauthenticated(self, client):
        """Test that creating users requires authentication."""
        response = client.post("/api/users", json={
            "full_name": "Test User",
            "email": "test@example.com"
        })
        assert response.status_code == 401


class TestUtilityFunctions:
    """Test utility functions from app.py."""

    def test_normalize_email_address(self):
        """Test email normalization."""
        from app import normalize_email_address

        assert normalize_email_address("  TEST@EXAMPLE.COM  ") == "test@example.com"
        assert normalize_email_address("test@example.com") == "test@example.com"
        assert normalize_email_address(None) == ""
        assert normalize_email_address("") == ""

    def test_is_valid_email_address(self):
        """Test email validation."""
        from app import is_valid_email_address

        assert is_valid_email_address("test@example.com") is True
        assert is_valid_email_address("invalid-email") is False
        assert is_valid_email_address("") is False
        assert is_valid_email_address("test@") is False

    def test_utc_now_iso(self):
        """Test UTC now ISO format."""
        from app import utc_now_iso

        result = utc_now_iso()
        assert isinstance(result, str)
        assert result.endswith("Z")
        assert "T" in result

    def test_parse_iso_datetime_to_utc(self):
        """Test ISO datetime parsing."""
        from app import parse_iso_datetime_to_utc

        # Test valid ISO string
        dt = parse_iso_datetime_to_utc("2023-01-01T12:00:00Z")
        assert dt is not None
        assert dt.year == 2023
        assert dt.month == 1
        assert dt.day == 1

        # Test invalid input
        assert parse_iso_datetime_to_utc("invalid") is None
        assert parse_iso_datetime_to_utc(None) is None