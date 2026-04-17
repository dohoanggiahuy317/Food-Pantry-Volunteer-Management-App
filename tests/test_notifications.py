"""
Unit tests for the notification system.
Tests all three notification functions across different scenarios:
  - Missing recipient email
  - Missing sender email (env not configured)
  - Missing API key (env not configured)
  - Resend library not installed
  - Resend API call failure
  - Successful send (mocked)
  - Edge cases: invalid datetimes, multiple roles, missing timezone
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — shared test data
# ---------------------------------------------------------------------------

VALID_RECIPIENT = {
    "email": "volunteer@example.com",
    "full_name": "Alice Smith",
    "timezone": "America/Chicago",
}

RECIPIENT_NO_EMAIL = {
    "email": "",
    "full_name": "No Email User",
}

VALID_SHIFT = {
    "shift_name": "Food Distribution",
    "start_time": "2025-06-15T09:00:00+00:00",
    "end_time": "2025-06-15T12:00:00+00:00",
}

MULTI_DAY_SHIFT = {
    "shift_name": "Overnight Shift",
    "start_time": "2025-06-15T22:00:00+00:00",
    "end_time": "2025-06-16T06:00:00+00:00",
}

BAD_TIMES_SHIFT = {
    "shift_name": "Bad Times Shift",
    "start_time": "not-a-date",
    "end_time": None,
}

VALID_PANTRY = {
    "name": "Downtown Food Pantry",
    "location_address": "123 Main St, Springfield",
}

VALID_ROLE = {
    "role_title": "Greeter",
}

SIGNUPS_SINGLE_ROLE = [
    {"role_title": "Greeter"},
]

SIGNUPS_MULTI_ROLE = [
    {"role_title": "Greeter"},
    {"role_title": "Greeter"},  # duplicate — should de-duplicate
    {"role_title": "Packer"},
]

SIGNUPS_EMPTY = []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_notifications_module():
    """
    Re-import the notifications module before each test so that module-level
    globals (RESEND_API_KEY, RESEND_FROM_EMAIL) can be patched cleanly.
    """
    mod_name = "notifications.notifications"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    yield
    if mod_name in sys.modules:
        del sys.modules[mod_name]


def _get_module(api_key: str = "test-key", from_email: str = "noreply@example.com"):
    """Import the module with the given env-level overrides already applied."""
    with patch.dict(
        "os.environ",
        {"RESEND_API_KEY": api_key, "RESEND_FROM_EMAIL": from_email},
        clear=False,
    ):
        mod = importlib.import_module("notifications.notifications")
        mod.RESEND_API_KEY = api_key
        mod.RESEND_FROM_EMAIL = from_email
        return mod


# ---------------------------------------------------------------------------
# send_signup_confirmation
# ---------------------------------------------------------------------------

class TestSendSignupConfirmation:

    def test_missing_recipient_email(self):
        mod = _get_module()
        result = mod.send_signup_confirmation(RECIPIENT_NO_EMAIL, VALID_SHIFT, VALID_PANTRY, VALID_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"

    def test_missing_sender_email(self):
        mod = _get_module(from_email="")
        result = mod.send_signup_confirmation(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, VALID_ROLE)
        assert result["ok"] is False
        assert result["code"] == "SENDER_EMAIL_MISSING"
        assert result["recipient_email"] == VALID_RECIPIENT["email"]

    def test_missing_api_key(self):
        mod = _get_module(api_key="")
        result = mod.send_signup_confirmation(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, VALID_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RESEND_API_KEY_MISSING"

    def test_resend_library_missing(self):
        mod = _get_module()
        with patch.dict("sys.modules", {"resend": None}):
            result = mod.send_signup_confirmation(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, VALID_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RESEND_LIBRARY_MISSING"

    def test_resend_send_fails(self):
        mod = _get_module()
        mock_resend = MagicMock()
        mock_resend.Emails.send.side_effect = Exception("network error")
        with patch.dict("sys.modules", {"resend": mock_resend}):
            result = mod.send_signup_confirmation(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, VALID_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RESEND_SEND_FAILED"
        assert "network error" in result["message"]

    def test_successful_send(self):
        mod = _get_module()
        mock_resend = MagicMock()
        mock_resend.Emails.send.return_value = {"id": "abc123"}
        with patch.dict("sys.modules", {"resend": mock_resend}):
            result = mod.send_signup_confirmation(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, VALID_ROLE)
        assert result["ok"] is True
        assert result["code"] == "SIGNUP_CONFIRMATION_SENT"
        assert result["recipient_email"] == VALID_RECIPIENT["email"]
        assert "Food Distribution" in result["subject"]
        assert result["provider"] == "resend"
        assert result["provider_response"] == {"id": "abc123"}

    def test_subject_contains_shift_name(self):
        mod = _get_module()
        mock_resend = MagicMock()
        mock_resend.Emails.send.return_value = {}
        with patch.dict("sys.modules", {"resend": mock_resend}):
            result = mod.send_signup_confirmation(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, VALID_ROLE)
        assert VALID_SHIFT["shift_name"] in result["subject"]

    def test_missing_shift_name_uses_fallback(self):
        mod = _get_module()
        mock_resend = MagicMock()
        mock_resend.Emails.send.return_value = {}
        shift_no_name = {**VALID_SHIFT, "shift_name": ""}
        with patch.dict("sys.modules", {"resend": mock_resend}):
            result = mod.send_signup_confirmation(VALID_RECIPIENT, shift_no_name, VALID_PANTRY, VALID_ROLE)
        assert result["ok"] is True
        # subject should still be built (with fallback text)
        assert result["subject"] is not None


# ---------------------------------------------------------------------------
# send_shift_update_notification
# ---------------------------------------------------------------------------

class TestSendShiftUpdateNotification:

    def test_missing_recipient_email(self):
        mod = _get_module()
        result = mod.send_shift_update_notification(RECIPIENT_NO_EMAIL, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"

    def test_missing_sender_email(self):
        mod = _get_module(from_email="")
        result = mod.send_shift_update_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is False
        assert result["code"] == "SENDER_EMAIL_MISSING"

    def test_missing_api_key(self):
        mod = _get_module(api_key="")
        result = mod.send_shift_update_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RESEND_API_KEY_MISSING"

    def test_resend_library_missing(self):
        mod = _get_module()
        with patch.dict("sys.modules", {"resend": None}):
            result = mod.send_shift_update_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RESEND_LIBRARY_MISSING"

    def test_resend_send_fails(self):
        mod = _get_module()
        mock_resend = MagicMock()
        mock_resend.Emails.send.side_effect = RuntimeError("timeout")
        with patch.dict("sys.modules", {"resend": mock_resend}):
            result = mod.send_shift_update_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RESEND_SEND_FAILED"

    def test_successful_send(self):
        mod = _get_module()
        mock_resend = MagicMock()
        mock_resend.Emails.send.return_value = {"id": "upd456"}
        with patch.dict("sys.modules", {"resend": mock_resend}):
            result = mod.send_shift_update_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is True
        assert result["code"] == "SHIFT_UPDATE_NOTIFICATION_SENT"
        assert result["recipient_email"] == VALID_RECIPIENT["email"]

    def test_multiple_roles_deduplication(self):
        """Duplicate role titles should appear only once in the notification."""
        mod = _get_module()
        mock_resend = MagicMock()
        mock_resend.Emails.send.return_value = {}
        with patch.dict("sys.modules", {"resend": mock_resend}):
            result = mod.send_shift_update_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_MULTI_ROLE)
        assert result["ok"] is True
        # Check that the email params were built — Emails.send was called once
        assert mock_resend.Emails.send.call_count == 1
        call_params = mock_resend.Emails.send.call_args[0][0]
        html = call_params["html"]
        assert html.count("Greeter") == 1   # de-duplicated
        assert "Packer" in html

    def test_empty_signups_uses_fallback_role(self):
        mod = _get_module()
        mock_resend = MagicMock()
        mock_resend.Emails.send.return_value = {}
        with patch.dict("sys.modules", {"resend": mock_resend}):
            result = mod.send_shift_update_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_EMPTY)
        assert result["ok"] is True
        call_params = mock_resend.Emails.send.call_args[0][0]
        assert "Volunteer role" in call_params["html"]  # fallback


# ---------------------------------------------------------------------------
# send_shift_cancellation_notification
# ---------------------------------------------------------------------------

class TestSendShiftCancellationNotification:

    def test_missing_recipient_email(self):
        mod = _get_module()
        result = mod.send_shift_cancellation_notification(RECIPIENT_NO_EMAIL, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"

    def test_missing_sender_email(self):
        mod = _get_module(from_email="")
        result = mod.send_shift_cancellation_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is False
        assert result["code"] == "SENDER_EMAIL_MISSING"

    def test_missing_api_key(self):
        mod = _get_module(api_key="")
        result = mod.send_shift_cancellation_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RESEND_API_KEY_MISSING"

    def test_resend_library_missing(self):
        mod = _get_module()
        with patch.dict("sys.modules", {"resend": None}):
            result = mod.send_shift_cancellation_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RESEND_LIBRARY_MISSING"

    def test_resend_send_fails(self):
        mod = _get_module()
        mock_resend = MagicMock()
        mock_resend.Emails.send.side_effect = ConnectionError("refused")
        with patch.dict("sys.modules", {"resend": mock_resend}):
            result = mod.send_shift_cancellation_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is False
        assert result["code"] == "RESEND_SEND_FAILED"

    def test_successful_send(self):
        mod = _get_module()
        mock_resend = MagicMock()
        mock_resend.Emails.send.return_value = {"id": "can789"}
        with patch.dict("sys.modules", {"resend": mock_resend}):
            result = mod.send_shift_cancellation_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert result["ok"] is True
        assert result["code"] == "SHIFT_CANCELLATION_NOTIFICATION_SENT"
        assert "cancelled" in result["subject"].lower()

    def test_subject_contains_shift_name(self):
        mod = _get_module()
        mock_resend = MagicMock()
        mock_resend.Emails.send.return_value = {}
        with patch.dict("sys.modules", {"resend": mock_resend}):
            result = mod.send_shift_cancellation_notification(VALID_RECIPIENT, VALID_SHIFT, VALID_PANTRY, SIGNUPS_SINGLE_ROLE)
        assert VALID_SHIFT["shift_name"] in result["subject"]


# ---------------------------------------------------------------------------
# Helper function edge cases
# ---------------------------------------------------------------------------

class TestFormatShiftWindow:

    def test_same_day_shift_format(self):
        mod = _get_module()
        result = mod._format_shift_window(VALID_SHIFT, "America/New_York")
        # same-day: shows date once with start-end time
        assert "June 15, 2025" in result
        assert " - " in result

    def test_multi_day_shift_format(self):
        mod = _get_module()
        result = mod._format_shift_window(MULTI_DAY_SHIFT, "America/New_York")
        # multi-day: both dates should appear
        assert "June 15" in result
        assert "June 16" in result

    def test_invalid_times_returns_fallback(self):
        mod = _get_module()
        result = mod._format_shift_window(BAD_TIMES_SHIFT, "America/New_York")
        assert result == "Time unavailable"

    def test_no_timezone_uses_default(self):
        mod = _get_module()
        result = mod._format_shift_window(VALID_SHIFT, None)
        # should not raise and should return a formatted string
        assert "2025" in result

    def test_invalid_timezone_falls_back_to_default(self):
        mod = _get_module()
        result = mod._format_shift_window(VALID_SHIFT, "Not/ATimezone")
        # should fall back to America/New_York and still format correctly
        assert "2025" in result


class TestNormalizedRoleTitles:

    def test_single_role(self):
        mod = _get_module()
        result = mod._normalized_role_titles([{"role_title": "Greeter"}])
        assert result == "Greeter"

    def test_multiple_unique_roles(self):
        mod = _get_module()
        result = mod._normalized_role_titles([{"role_title": "Greeter"}, {"role_title": "Packer"}])
        assert result == "Greeter, Packer"

    def test_duplicate_roles_deduplicated(self):
        mod = _get_module()
        result = mod._normalized_role_titles([{"role_title": "Greeter"}, {"role_title": "Greeter"}])
        assert result == "Greeter"

    def test_empty_list_returns_fallback(self):
        mod = _get_module()
        result = mod._normalized_role_titles([])
        assert result == "Volunteer role"

    def test_missing_role_title_uses_fallback(self):
        mod = _get_module()
        result = mod._normalized_role_titles([{"role_title": ""}])
        assert result == "Volunteer role"
