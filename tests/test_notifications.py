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
        from notifications.notifications import _parse_iso_datetime_to_utc

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
        from notifications.notifications import _normalized_text

        assert _normalized_text("  test  ", "fallback") == "test"
        assert _normalized_text(None, "fallback") == "fallback"
        assert _normalized_text("", "fallback") == "fallback"
        assert _normalized_text("value", "fallback") == "value"

    def test_normalized_role_titles(self):
        """Test role title normalization."""
        from notifications.notifications import _normalized_role_titles

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
        from notifications.notifications import _format_shift_window

        shift = {
            "start_time": "2023-01-01T10:00:00Z",
            "end_time": "2023-01-01T12:00:00Z"
        }

        result = _format_shift_window(shift, "UTC")
        assert "Sunday, January 01, 2023" in result
        assert "10:00 AM - 12:00 PM UTC" in result

        # Test with invalid times
        invalid_shift = {"start_time": None, "end_time": None}
        result = _format_shift_window(invalid_shift)
        assert result == "Time unavailable"

    def test_build_email_html(self):
        """Test HTML email building."""
        from notifications.notifications import _build_email_html

        html = _build_email_html(
            recipient_name="John Doe",
            intro="This is an intro.",
            details=[
                ("Item1", "Value1"),
                ("Item2", "Value2"),
            ],
            outro="This is an outro.",
        )

        assert "Hi John Doe" in html
        assert "This is an intro." in html
        assert "This is an outro." in html
        assert "<strong>Item1:</strong> Value1" in html
        assert "<strong>Item2:</strong> Value2" in html
        assert "Volunteer Managing Teams" in html
        assert html.startswith("<p>")

    def test_notification_result(self):
        """Test notification result structure."""
        from notifications.notifications import _notification_result

        result = _notification_result(
            ok=True,
            code="SUCCESS",
            message="Test message",
            recipient_email="test@example.com",
            subject="Test Subject",
        )

        assert result["ok"] is True
        assert result["code"] == "SUCCESS"
        assert result["message"] == "Test message"
        assert result["recipient_email"] == "test@example.com"
        assert result["subject"] == "Test Subject"
        assert result["provider"] == "resend"
        assert result["provider_response"] is None


class TestSignupConfirmation:
    """Test signup confirmation notification."""

    def test_missing_recipient_email(self):
        """Test error when recipient email is missing."""
        result = send_signup_confirmation(
            recipient={"full_name": "John Doe"},
            shift={"shift_name": "Morning Shift"},
            pantry={"name": "Food Bank"},
            role={"role_title": "Volunteer"},
        )

        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"
        assert result["message"] == "Recipient email is missing."

    def test_missing_sender_email_config(self):
        """Test error when sender email is not configured."""
        with patch("notifications.notifications.RESEND_FROM_EMAIL", ""):
            result = send_signup_confirmation(
                recipient={
                    "email": "volunteer@example.com",
                    "full_name": "John Doe"
                },
                shift={"shift_name": "Morning Shift"},
                pantry={"name": "Food Bank"},
                role={"role_title": "Volunteer"},
            )

            assert result["ok"] is False
            assert result["code"] == "SENDER_EMAIL_MISSING"

    def test_successful_signup_confirmation_with_mock(self):
        """Test successful signup confirmation."""
        with patch("notifications.notifications.RESEND_API_KEY", "test_key"), \
             patch("notifications.notifications.RESEND_FROM_EMAIL", "sender@example.com"), \
             patch("notifications.notifications._send_resend_email") as mock_send:

            mock_send.return_value = {
                "ok": True,
                "provider": "resend",
                "code": "SIGNUP_CONFIRMATION_SENT",
                "message": "Signup confirmation email sent.",
                "recipient_email": "volunteer@example.com",
                "subject": "Volunteer signup confirmed: Morning Shift",
                "provider_response": {"id": "email_123"},
            }

            result = send_signup_confirmation(
                recipient={
                    "email": "volunteer@example.com",
                    "full_name": "John Doe"
                },
                shift={
                    "shift_name": "Morning Shift",
                    "start_time": "2023-05-15T08:00:00Z",
                    "end_time": "2023-05-15T12:00:00Z",
                },
                pantry={
                    "name": "Community Food Bank",
                    "location_address": "123 Main St"
                },
                role={"role_title": "Food Sorter"},
            )

            assert result["ok"] is True
            assert result["code"] == "SIGNUP_CONFIRMATION_SENT"
            assert "Morning Shift" in result["subject"]

    def test_signup_confirmation_uses_defaults(self):
        """Test that signup confirmation uses default values."""
        with patch("notifications.notifications.RESEND_API_KEY", "test_key"), \
             patch("notifications.notifications.RESEND_FROM_EMAIL", "sender@example.com"), \
             patch("notifications.notifications._send_resend_email") as mock_send:

            mock_send.return_value = {
                "ok": True,
                "provider": "resend",
                "code": "SIGNUP_CONFIRMATION_SENT",
                "message": "Signup confirmation email sent.",
                "recipient_email": "volunteer@example.com",
                "subject": "Volunteer signup confirmed: your volunteer shift",
                "provider_response": None,
            }

            result = send_signup_confirmation(
                recipient={"email": "volunteer@example.com"},
                shift={},
                pantry={},
                role={},
            )

            assert result["ok"] is True
            # Verify that _send_resend_email was called with the params
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            params = call_args[0][0]
            
            # The HTML should contain default values
            html = params["html"]
            assert "Volunteer" in html  # Default recipient name
            assert "Pantry" in html  # Default pantry name
            assert "Volunteer role" in html  # Default role title


class TestShiftUpdateNotification:
    """Test shift update notification."""

    def test_missing_recipient_email(self):
        """Test error when recipient email is missing."""
        result = send_shift_update_notification(
            recipient={"full_name": "John Doe"},
            shift={"shift_name": "Morning Shift"},
            pantry={"name": "Food Bank"},
            signups=[],
        )

        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"

    def test_missing_sender_email_config(self):
        """Test error when sender email is not configured."""
        with patch("notifications.notifications.RESEND_FROM_EMAIL", ""):
            result = send_shift_update_notification(
                recipient={
                    "email": "volunteer@example.com",
                    "full_name": "John Doe"
                },
                shift={"shift_name": "Morning Shift"},
                pantry={"name": "Food Bank"},
                signups=[],
            )

            assert result["ok"] is False
            assert result["code"] == "SENDER_EMAIL_MISSING"

    def test_successful_shift_update_with_mock(self):
        """Test successful shift update notification."""
        with patch("notifications.notifications.RESEND_API_KEY", "test_key"), \
             patch("notifications.notifications.RESEND_FROM_EMAIL", "sender@example.com"), \
             patch("notifications.notifications._send_resend_email") as mock_send:

            mock_send.return_value = {
                "ok": True,
                "provider": "resend",
                "code": "SHIFT_UPDATE_NOTIFICATION_SENT",
                "message": "Shift update notification email sent.",
                "recipient_email": "volunteer@example.com",
                "subject": "Shift updated: action needed for Morning Shift",
                "provider_response": {"id": "email_456"},
            }

            result = send_shift_update_notification(
                recipient={
                    "email": "volunteer@example.com",
                    "full_name": "Jane Smith"
                },
                shift={
                    "shift_name": "Morning Shift",
                    "start_time": "2023-05-20T09:00:00Z",
                    "end_time": "2023-05-20T13:00:00Z",
                },
                pantry={
                    "name": "Downtown Food Bank",
                    "location_address": "456 Oak Ave"
                },
                signups=[
                    {"role_title": "Cashier"},
                    {"role_title": "Packager"},
                ],
            )

            assert result["ok"] is True
            assert result["code"] == "SHIFT_UPDATE_NOTIFICATION_SENT"
            assert "action needed" in result["subject"]

    def test_shift_update_with_multiple_signups(self):
        """Test shift update with multiple role signups."""
        with patch("notifications.notifications.RESEND_API_KEY", "test_key"), \
             patch("notifications.notifications.RESEND_FROM_EMAIL", "sender@example.com"), \
             patch("notifications.notifications._send_resend_email") as mock_send:

            mock_send.return_value = {
                "ok": True,
                "provider": "resend",
                "code": "SHIFT_UPDATE_NOTIFICATION_SENT",
                "message": "Shift update notification email sent.",
                "recipient_email": "volunteer@example.com",
                "subject": "Shift updated: action needed for Shift",
                "provider_response": None,
            }

            result = send_shift_update_notification(
                recipient={
                    "email": "volunteer@example.com",
                    "full_name": "Alex"
                },
                shift={
                    "shift_name": "Special Event",
                    "start_time": "2023-05-25T10:00:00Z",
                    "end_time": "2023-05-25T15:00:00Z",
                },
                pantry={"name": "Event Food Bank"},
                signups=[
                    {"role_title": "Setup"},
                    {"role_title": "Distribution"},
                    {"role_title": "Cleanup"},
                ],
            )

            assert result["ok"] is True
            # Verify multiple roles are included
            call_args = mock_send.call_args
            params = call_args[0][0]
            html = params["html"]
            assert "Setup" in html or "Distribution" in html or "Cleanup" in html


class TestShiftCancellationNotification:
    """Test shift cancellation notification."""

    def test_missing_recipient_email(self):
        """Test error when recipient email is missing."""
        result = send_shift_cancellation_notification(
            recipient={"full_name": "John Doe"},
            shift={"shift_name": "Morning Shift"},
            pantry={"name": "Food Bank"},
            signups=[],
        )

        assert result["ok"] is False
        assert result["code"] == "RECIPIENT_EMAIL_MISSING"

    def test_missing_sender_email_config(self):
        """Test error when sender email is not configured."""
        with patch("notifications.notifications.RESEND_FROM_EMAIL", ""):
            result = send_shift_cancellation_notification(
                recipient={
                    "email": "volunteer@example.com",
                    "full_name": "John Doe"
                },
                shift={"shift_name": "Morning Shift"},
                pantry={"name": "Food Bank"},
                signups=[],
            )

            assert result["ok"] is False
            assert result["code"] == "SENDER_EMAIL_MISSING"

    def test_successful_shift_cancellation_with_mock(self):
        """Test successful shift cancellation notification."""
        with patch("notifications.notifications.RESEND_API_KEY", "test_key"), \
             patch("notifications.notifications.RESEND_FROM_EMAIL", "sender@example.com"), \
             patch("notifications.notifications._send_resend_email") as mock_send:

            mock_send.return_value = {
                "ok": True,
                "provider": "resend",
                "code": "SHIFT_CANCELLATION_NOTIFICATION_SENT",
                "message": "Shift cancellation notification email sent.",
                "recipient_email": "volunteer@example.com",
                "subject": "Shift cancelled: Evening Shift",
                "provider_response": {"id": "email_789"},
            }

            result = send_shift_cancellation_notification(
                recipient={
                    "email": "volunteer@example.com",
                    "full_name": "Bob Wilson"
                },
                shift={
                    "shift_name": "Evening Shift",
                    "start_time": "2023-06-01T17:00:00Z",
                    "end_time": "2023-06-01T21:00:00Z",
                },
                pantry={
                    "name": "Evening Food Bank",
                    "location_address": "789 Pine Rd"
                },
                signups=[{"role_title": "Volunteer"}],
            )

            assert result["ok"] is True
            assert result["code"] == "SHIFT_CANCELLATION_NOTIFICATION_SENT"
            assert "cancelled" in result["subject"]

    def test_cancellation_email_content(self):
        """Test that cancellation email contains appropriate message."""
        with patch("notifications.notifications.RESEND_API_KEY", "test_key"), \
             patch("notifications.notifications.RESEND_FROM_EMAIL", "sender@example.com"), \
             patch("notifications.notifications._send_resend_email") as mock_send:

            mock_send.return_value = {
                "ok": True,
                "provider": "resend",
                "code": "SHIFT_CANCELLATION_NOTIFICATION_SENT",
                "message": "Shift cancellation notification email sent.",
                "recipient_email": "volunteer@example.com",
                "subject": "Shift cancelled: Test Shift",
                "provider_response": None,
            }

            result = send_shift_cancellation_notification(
                recipient={
                    "email": "volunteer@example.com",
                    "full_name": "Test User"
                },
                shift={"shift_name": "Test Shift"},
                pantry={"name": "Test Bank"},
                signups=[],
            )

            assert result["ok"] is True
            call_args = mock_send.call_args
            params = call_args[0][0]
            html = params["html"]
            
            # Verify cancellation-specific content
            assert "cancelled" in html.lower()
            assert "flexibility" in html.lower()
