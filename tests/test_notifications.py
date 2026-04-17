import sys
from pathlib import Path

# Add backend directory to Python path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

import pytest
from unittest.mock import patch, MagicMock
from notifications import (
    send_signup_confirmation,
    send_shift_update_notification,
    send_shift_cancellation_notification,
    NotificationResult
)



class TestNotificationHelpers:
    """Test notification helper functions."""

    def test_parse_iso_datetime_to_utc(self):
        """Test ISO datetime parsing."""
        from backend.notifications.notifications import _parse_iso_datetime_to_utc

        # Test valid datetime string
        dt = _parse_iso_datetime_to_utc("2023-01-01T12:00:00Z")
        assert dt is not None
        assert dt.year == 2023
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 12

        # Test invalid input
        assert _parse_iso_datetime_to_utc("invalid") is None
        assert _parse_iso_datetime_to_utc(None) is None

    def test_normalized_text(self):
        """Test text normalization."""
        from backend.notifications.notifications import _normalized_text

        assert _normalized_text("  test  ", "fallback") == "test"
        assert _normalized_text(None, "fallback") == "fallback"
        assert _normalized_text("", "fallback") == "fallback"
        assert _normalized_text("value", "fallback") == "value"

    def test_normalized_role_titles(self):
        """Test role title normalization."""
        from backend.notifications.notifications import _normalized_role_titles

        signups = [
            {"role_title": "Role 1"},
            {"role_title": "Role 1"},  # duplicate
            {"role_title": "Role 2"},
            {"role_title": None}
        ]

        result = _normalized_role_titles(signups)
        assert "Role 1" in result
        assert "Role 2" in result
        assert result.count("Role 1") == 1  # no duplicates

    def test_format_shift_window(self):
        """Test shift window formatting."""
        from backend.notifications.notifications import _format_shift_window

        shift = {
            "start_time": "2023-01-01T10:00:00Z",
            "end_time": "2023-01-01T12:00:00Z"
        }

        result = _format_shift_window(shift)
        assert "Sunday, January 01, 2023" in result
        assert "10:00 AM UTC" in result
        assert "12:00 PM UTC" in result

        # Test with invalid times
        invalid_shift = {"start_time": None, "end_time": None}
        result = _format_shift_window(invalid_shift)
        assert result == "Time unavailable"