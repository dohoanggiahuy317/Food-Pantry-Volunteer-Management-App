"""
Notifications Component Tests

Tests all six send_* functions in notifications/notifications.py in isolation.
The Resend module is replaced by the mock_resend_send fixture. No MySQL or
external API access is required; all inputs are plain dicts.

Run with: pytest tests/component/test_notifications_component.py -v -m component
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

pytestmark = pytest.mark.component

# ── Test data builders ────────────────────────────────────────────────────────

def _recipient(*, email="volunteer@example.com", name="Test Volunteer",
               timezone="America/New_York"):
    return {"email": email, "full_name": name, "timezone": timezone}


def _pantry(*, name="Elm Street Pantry", address="1 Elm St, Boston, MA"):
    return {"name": name, "location_address": address}


def _shift(*, name="Morning Distribution",
           start="2026-06-15T17:00:00Z", end="2026-06-15T19:00:00Z"):
    return {"shift_name": name, "start_time": start, "end_time": end}


def _role(*, title="Packer"):
    return {"role_title": title}


def _signups(*titles):
    return [{"role_title": t} for t in titles]


def _roles(*titles):
    return [{"role_title": t} for t in titles]


def _recurrence(*, interval=1, weekdays=None, end_mode="COUNT",
                occurrence_count=4, until_date=None):
    return {
        "interval_weeks": interval,
        "weekdays": weekdays or ["MO"],
        "end_mode": end_mode,
        "occurrence_count": occurrence_count,
        "until_date": until_date,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _html_from_call(mock_resend_send):
    """Extract the html body from the captured Resend call."""
    return mock_resend_send.call_args[0][0]["html"]


def _subject_from_call(mock_resend_send):
    return mock_resend_send.call_args[0][0]["subject"]


def _to_from_call(mock_resend_send):
    return mock_resend_send.call_args[0][0]["to"]


# ── send_signup_confirmation ──────────────────────────────────────────────────

class TestSendSignupConfirmation:
    def test_happy_path_calls_resend_once(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        result = send_signup_confirmation(_recipient(), _shift(), _pantry(), _role())
        assert result["ok"] is True
        assert result["code"] == "SIGNUP_CONFIRMATION_SENT"
        mock_resend_send.assert_called_once()

    def test_sends_to_correct_email_address(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        send_signup_confirmation(
            _recipient(email="alice@example.com"), _shift(), _pantry(), _role()
        )
        assert _to_from_call(mock_resend_send) == ["alice@example.com"]

    def test_subject_contains_shift_name(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        send_signup_confirmation(
            _recipient(), _shift(name="Tuesday Bag Pack"), _pantry(), _role()
        )
        assert "Tuesday Bag Pack" in _subject_from_call(mock_resend_send)

    def test_html_contains_pantry_name(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        send_signup_confirmation(
            _recipient(), _shift(), _pantry(name="Maple Ave Food Bank"), _role()
        )
        assert "Maple Ave Food Bank" in _html_from_call(mock_resend_send)

    def test_html_contains_role_title(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        send_signup_confirmation(
            _recipient(), _shift(), _pantry(), _role(title="Lead Sorter")
        )
        assert "Lead Sorter" in _html_from_call(mock_resend_send)

    def test_html_contains_location_address(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        send_signup_confirmation(
            _recipient(), _shift(), _pantry(address="99 Oak Blvd"), _role()
        )
        assert "99 Oak Blvd" in _html_from_call(mock_resend_send)

    def test_html_greets_recipient_by_name(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        send_signup_confirmation(
            _recipient(name="Jordan Smith"), _shift(), _pantry(), _role()
        )
        assert "Jordan Smith" in _html_from_call(mock_resend_send)

    def test_provider_response_stored_in_result(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        result = send_signup_confirmation(_recipient(), _shift(), _pantry(), _role())
        assert result["provider_response"] == {"id": "mock-email-id-abc123"}

    def test_recipient_email_missing_returns_error_without_calling_resend(
        self, mock_resend_send
    ):
        from notifications.notifications import send_signup_confirmation
        result = send_signup_confirmation(
            _recipient(email=""), _shift(), _pantry(), _role()
        )
        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"
        mock_resend_send.assert_not_called()

    def test_missing_api_key_returns_error_without_calling_resend(self, mock_resend_send):
        from notifications import notifications as notifs
        from notifications.notifications import send_signup_confirmation
        with patch.object(notifs, "RESEND_API_KEY", ""):
            result = send_signup_confirmation(_recipient(), _shift(), _pantry(), _role())
        assert result["ok"] is False
        assert result["code"] == "RESEND_API_KEY_MISSING"
        mock_resend_send.assert_not_called()

    def test_missing_from_email_returns_error_without_calling_resend(self, mock_resend_send):
        from notifications import notifications as notifs
        from notifications.notifications import send_signup_confirmation
        with patch.object(notifs, "RESEND_FROM_EMAIL", ""):
            result = send_signup_confirmation(_recipient(), _shift(), _pantry(), _role())
        assert result["ok"] is False
        assert result["code"] == "SENDER_EMAIL_MISSING"
        mock_resend_send.assert_not_called()

    def test_resend_exception_returns_send_failed(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        mock_resend_send.side_effect = Exception("network timeout")
        result = send_signup_confirmation(_recipient(), _shift(), _pantry(), _role())
        assert result["ok"] is False
        assert result["code"] == "RESEND_SEND_FAILED"


# ── Timezone formatting ───────────────────────────────────────────────────────

class TestTimezoneFormatting:
    def test_shift_time_formatted_in_recipient_timezone(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        # 17:00 UTC = 12:00 PM CDT (America/Chicago, UTC-5 in summer)
        send_signup_confirmation(
            _recipient(timezone="America/Chicago"),
            _shift(start="2026-06-15T17:00:00Z", end="2026-06-15T19:00:00Z"),
            _pantry(),
            _role(),
        )
        html = _html_from_call(mock_resend_send)
        assert "12:00 PM" in html
        assert "CDT" in html

    def test_invalid_timezone_falls_back_to_eastern(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        send_signup_confirmation(
            _recipient(timezone="Not/A/Timezone"),
            _shift(start="2026-06-15T17:00:00Z", end="2026-06-15T19:00:00Z"),
            _pantry(),
            _role(),
        )
        html = _html_from_call(mock_resend_send)
        # America/New_York fallback — should not raise and should show ET
        assert "EDT" in html or "EST" in html

    def test_multiday_shift_shows_both_dates(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        # EDT = UTC-4. To cross calendar midnight in EDT the end time must be
        # after 04:00 UTC (= 00:00 EDT).
        # start: 2026-06-15T22:00:00Z = 18:00 EDT on June 15
        # end:   2026-06-16T06:00:00Z = 02:00 EDT on June 16
        send_signup_confirmation(
            _recipient(timezone="America/New_York"),
            _shift(start="2026-06-15T22:00:00Z", end="2026-06-16T06:00:00Z"),
            _pantry(),
            _role(),
        )
        html = _html_from_call(mock_resend_send)
        assert "June 15" in html
        assert "June 16" in html

    def test_utc_timezone_shows_utc_label(self, mock_resend_send):
        from notifications.notifications import send_signup_confirmation
        send_signup_confirmation(
            _recipient(timezone="UTC"),
            _shift(start="2026-06-15T14:00:00Z", end="2026-06-15T16:00:00Z"),
            _pantry(),
            _role(),
        )
        html = _html_from_call(mock_resend_send)
        assert "UTC" in html


# ── send_shift_update_notification ───────────────────────────────────────────

class TestSendShiftUpdateNotification:
    def test_happy_path_sends_email(self, mock_resend_send):
        from notifications.notifications import send_shift_update_notification
        result = send_shift_update_notification(
            _recipient(), _shift(), _pantry(), _signups("Packer")
        )
        assert result["ok"] is True
        assert result["code"] == "SHIFT_UPDATE_NOTIFICATION_SENT"
        mock_resend_send.assert_called_once()

    def test_subject_contains_shift_name_and_action_prefix(self, mock_resend_send):
        from notifications.notifications import send_shift_update_notification
        send_shift_update_notification(
            _recipient(), _shift(name="Friday Sort"), _pantry(), _signups("Packer")
        )
        subject = _subject_from_call(mock_resend_send)
        assert "Friday Sort" in subject
        assert "action needed" in subject.lower()

    def test_html_lists_role_titles_from_signups(self, mock_resend_send):
        from notifications.notifications import send_shift_update_notification
        send_shift_update_notification(
            _recipient(), _shift(), _pantry(), _signups("Packer", "Driver")
        )
        html = _html_from_call(mock_resend_send)
        assert "Packer" in html
        assert "Driver" in html

    def test_duplicate_role_titles_are_deduplicated(self, mock_resend_send):
        from notifications.notifications import send_shift_update_notification
        send_shift_update_notification(
            _recipient(), _shift(), _pantry(),
            _signups("Packer", "Packer", "Driver")
        )
        html = _html_from_call(mock_resend_send)
        # "Packer" should appear only once in the role list
        assert html.count("Packer") == 1

    def test_empty_signups_uses_default_role_title(self, mock_resend_send):
        from notifications.notifications import send_shift_update_notification
        send_shift_update_notification(_recipient(), _shift(), _pantry(), [])
        html = _html_from_call(mock_resend_send)
        assert "Volunteer role" in html

    def test_missing_recipient_email_returns_error(self, mock_resend_send):
        from notifications.notifications import send_shift_update_notification
        result = send_shift_update_notification(
            _recipient(email=""), _shift(), _pantry(), _signups("Packer")
        )
        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"
        mock_resend_send.assert_not_called()


# ── send_shift_cancellation_notification ─────────────────────────────────────

class TestSendShiftCancellationNotification:
    def test_happy_path_sends_email(self, mock_resend_send):
        from notifications.notifications import send_shift_cancellation_notification
        result = send_shift_cancellation_notification(
            _recipient(), _shift(), _pantry(), _signups("Packer")
        )
        assert result["ok"] is True
        assert result["code"] == "SHIFT_CANCELLATION_NOTIFICATION_SENT"

    def test_subject_contains_shift_name(self, mock_resend_send):
        from notifications.notifications import send_shift_cancellation_notification
        send_shift_cancellation_notification(
            _recipient(), _shift(name="Monday Drop-In"), _pantry(), _signups("Packer")
        )
        assert "Monday Drop-In" in _subject_from_call(mock_resend_send)
        assert "cancelled" in _subject_from_call(mock_resend_send).lower()

    def test_html_contains_cancellation_language(self, mock_resend_send):
        from notifications.notifications import send_shift_cancellation_notification
        send_shift_cancellation_notification(
            _recipient(), _shift(), _pantry(), _signups("Packer")
        )
        html = _html_from_call(mock_resend_send)
        assert "cancelled" in html.lower()

    def test_missing_recipient_email_returns_error(self, mock_resend_send):
        from notifications.notifications import send_shift_cancellation_notification
        result = send_shift_cancellation_notification(
            _recipient(email=""), _shift(), _pantry(), _signups("Packer")
        )
        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"
        mock_resend_send.assert_not_called()


# ── send_new_shift_subscriber_notification ────────────────────────────────────

class TestSendNewShiftSubscriberNotification:
    def test_happy_path_sends_email(self, mock_resend_send):
        from notifications.notifications import send_new_shift_subscriber_notification
        result = send_new_shift_subscriber_notification(
            _recipient(), _pantry(), _shift(), _roles("Driver", "Sorter")
        )
        assert result["ok"] is True
        assert result["code"] == "NEW_SHIFT_SUBSCRIBER_NOTIFICATION_SENT"

    def test_subject_contains_shift_name(self, mock_resend_send):
        from notifications.notifications import send_new_shift_subscriber_notification
        send_new_shift_subscriber_notification(
            _recipient(), _pantry(), _shift(name="Saturday Special"), _roles("Packer")
        )
        assert "Saturday Special" in _subject_from_call(mock_resend_send)

    def test_html_contains_role_titles_from_roles_list(self, mock_resend_send):
        from notifications.notifications import send_new_shift_subscriber_notification
        send_new_shift_subscriber_notification(
            _recipient(), _pantry(), _shift(), _roles("Driver", "Sorter")
        )
        html = _html_from_call(mock_resend_send)
        assert "Driver" in html
        assert "Sorter" in html

    def test_empty_roles_shows_fallback_message(self, mock_resend_send):
        from notifications.notifications import send_new_shift_subscriber_notification
        send_new_shift_subscriber_notification(
            _recipient(), _pantry(), _shift(), []
        )
        html = _html_from_call(mock_resend_send)
        assert "Roles will be announced soon" in html

    def test_missing_recipient_email_returns_error(self, mock_resend_send):
        from notifications.notifications import send_new_shift_subscriber_notification
        result = send_new_shift_subscriber_notification(
            _recipient(email=""), _pantry(), _shift(), _roles("Packer")
        )
        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"
        mock_resend_send.assert_not_called()


# ── send_new_shift_series_subscriber_notification ────────────────────────────

class TestSendNewShiftSeriesSubscriberNotification:
    def _call(self, mock_resend_send, *, recurrence=None, occurrences=None):
        from notifications.notifications import (
            send_new_shift_series_subscriber_notification,
        )
        return send_new_shift_series_subscriber_notification(
            _recipient(),
            _pantry(),
            _shift(),
            _roles("Packer"),
            recurrence or _recurrence(),
            created_shift_count=4,
            preview_occurrences=occurrences or [
                _shift(start=f"2026-10-0{i+5}T09:00:00Z",
                       end=f"2026-10-0{i+5}T12:00:00Z")
                for i in range(3)
            ],
        )

    def test_happy_path_sends_email(self, mock_resend_send):
        result = self._call(mock_resend_send)
        assert result["ok"] is True
        assert result["code"] == "NEW_SHIFT_SERIES_SUBSCRIBER_NOTIFICATION_SENT"

    def test_subject_contains_shift_name(self, mock_resend_send):
        from notifications.notifications import (
            send_new_shift_series_subscriber_notification,
        )
        send_new_shift_series_subscriber_notification(
            _recipient(), _pantry(), _shift(name="Weekly Bread Run"),
            _roles("Packer"), _recurrence(), 3, []
        )
        assert "Weekly Bread Run" in _subject_from_call(mock_resend_send)

    def test_html_contains_weekly_recurrence_summary(self, mock_resend_send):
        self._call(
            mock_resend_send,
            recurrence=_recurrence(interval=1, weekdays=["MO", "WE"],
                                   end_mode="COUNT", occurrence_count=4),
        )
        html = _html_from_call(mock_resend_send)
        assert "every week" in html
        assert "Mon" in html
        assert "Wed" in html
        assert "4 occurrence" in html

    def test_html_contains_biweekly_recurrence_summary(self, mock_resend_send):
        self._call(
            mock_resend_send,
            recurrence=_recurrence(interval=2, weekdays=["FR"],
                                   end_mode="COUNT", occurrence_count=6),
        )
        html = _html_from_call(mock_resend_send)
        assert "every 2 weeks" in html
        assert "Fri" in html

    def test_html_contains_until_date_recurrence_summary(self, mock_resend_send):
        self._call(
            mock_resend_send,
            recurrence=_recurrence(interval=1, weekdays=["TU"],
                                   end_mode="UNTIL", until_date="2026-12-31"),
        )
        html = _html_from_call(mock_resend_send)
        assert "until 2026-12-31" in html

    def test_preview_shows_max_three_occurrences(self, mock_resend_send):
        four_occurrences = [
            _shift(start=f"2026-10-{5 + i * 7:02d}T09:00:00Z",
                   end=f"2026-10-{5 + i * 7:02d}T12:00:00Z")
            for i in range(4)
        ]
        self._call(mock_resend_send, occurrences=four_occurrences)
        html = _html_from_call(mock_resend_send)
        # The preview joins items with " | "; 3 items → 2 separators
        assert html.count(" | ") == 2

    def test_missing_recipient_email_returns_error(self, mock_resend_send):
        from notifications.notifications import (
            send_new_shift_series_subscriber_notification,
        )
        result = send_new_shift_series_subscriber_notification(
            _recipient(email=""), _pantry(), _shift(),
            _roles("Packer"), _recurrence(), 4, []
        )
        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"
        mock_resend_send.assert_not_called()


# ── send_shift_help_broadcast ─────────────────────────────────────────────────

class TestSendShiftHelpBroadcast:
    def test_happy_path_sends_email(self, mock_resend_send):
        from notifications.notifications import send_shift_help_broadcast
        result = send_shift_help_broadcast(_recipient(), _shift(), _pantry())
        assert result["ok"] is True
        assert result["code"] == "SHIFT_HELP_BROADCAST_SENT"
        mock_resend_send.assert_called_once()

    def test_sends_to_correct_email_address(self, mock_resend_send):
        from notifications.notifications import send_shift_help_broadcast
        send_shift_help_broadcast(_recipient(email="target@example.com"), _shift(), _pantry())
        assert _to_from_call(mock_resend_send) == ["target@example.com"]

    def test_subject_contains_help_needed_and_shift_name(self, mock_resend_send):
        from notifications.notifications import send_shift_help_broadcast
        send_shift_help_broadcast(
            _recipient(), _shift(name="Thursday Soup Kitchen"), _pantry()
        )
        subject = _subject_from_call(mock_resend_send)
        assert "Help needed" in subject
        assert "Thursday Soup Kitchen" in subject

    def test_html_contains_understaffed_language(self, mock_resend_send):
        from notifications.notifications import send_shift_help_broadcast
        send_shift_help_broadcast(_recipient(), _shift(), _pantry())
        html = _html_from_call(mock_resend_send)
        assert "understaffed" in html.lower()

    def test_html_contains_pantry_name_and_location(self, mock_resend_send):
        from notifications.notifications import send_shift_help_broadcast
        send_shift_help_broadcast(
            _recipient(),
            _shift(),
            _pantry(name="Central Pantry", address="5 Central Ave"),
        )
        html = _html_from_call(mock_resend_send)
        assert "Central Pantry" in html
        assert "5 Central Ave" in html

    def test_html_greets_recipient_by_name(self, mock_resend_send):
        from notifications.notifications import send_shift_help_broadcast
        send_shift_help_broadcast(_recipient(name="Robin Lee"), _shift(), _pantry())
        assert "Robin Lee" in _html_from_call(mock_resend_send)

    def test_missing_recipient_email_returns_error_without_calling_resend(
        self, mock_resend_send
    ):
        from notifications.notifications import send_shift_help_broadcast
        result = send_shift_help_broadcast(_recipient(email=""), _shift(), _pantry())
        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"
        mock_resend_send.assert_not_called()

    def test_missing_api_key_returns_error(self, mock_resend_send):
        from notifications import notifications as notifs
        from notifications.notifications import send_shift_help_broadcast
        with patch.object(notifs, "RESEND_API_KEY", ""):
            result = send_shift_help_broadcast(_recipient(), _shift(), _pantry())
        assert result["ok"] is False
        assert result["code"] == "RESEND_API_KEY_MISSING"
        mock_resend_send.assert_not_called()

    def test_missing_from_email_returns_error(self, mock_resend_send):
        from notifications import notifications as notifs
        from notifications.notifications import send_shift_help_broadcast
        with patch.object(notifs, "RESEND_FROM_EMAIL", ""):
            result = send_shift_help_broadcast(_recipient(), _shift(), _pantry())
        assert result["ok"] is False
        assert result["code"] == "SENDER_EMAIL_MISSING"
        mock_resend_send.assert_not_called()

    def test_resend_exception_returns_send_failed(self, mock_resend_send):
        from notifications.notifications import send_shift_help_broadcast
        mock_resend_send.side_effect = Exception("API unavailable")
        result = send_shift_help_broadcast(_recipient(), _shift(), _pantry())
        assert result["ok"] is False
        assert result["code"] == "RESEND_SEND_FAILED"
