from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

RESEND_API_KEY = str(os.getenv("RESEND_API_KEY") or "").strip()
RESEND_FROM_EMAIL = str(os.getenv("RESEND_FROM_EMAIL") or "").strip()
DEFAULT_PANTRY_NAME = "Pantry"
DEFAULT_ROLE_TITLE = "Volunteer role"
DEFAULT_RECIPIENT_NAME = "Volunteer"
DEFAULT_LOCATION = "Location unavailable"
DEFAULT_SHIFT_NAME = "your volunteer shift"
TIME_UNAVAILABLE_LABEL = "Time unavailable"


class NotificationResult(TypedDict):
    ok: bool
    provider: str
    code: str
    message: str
    recipient_email: str | None
    subject: str | None
    provider_response: Any | None


def _parse_iso_datetime_to_utc(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalized_text(value: Any, fallback: str) -> str:
    return str(value or fallback).strip()


def _format_shift_window(shift: dict[str, Any]) -> str:
    start_time = _parse_iso_datetime_to_utc(shift.get("start_time"))
    end_time = _parse_iso_datetime_to_utc(shift.get("end_time"))
    if not start_time or not end_time:
        return TIME_UNAVAILABLE_LABEL
    return (
        f"{start_time.strftime('%A, %B %d, %Y at %I:%M %p UTC')} "
        f"to {end_time.strftime('%I:%M %p UTC')}"
    )


def _build_signup_confirmation_html(
    recipient_name: str,
    pantry_name: str,
    role_title: str,
    shift_window: str,
    location: str,
) -> str:
    return (
        f"<p>Hi {recipient_name},</p>"
        "<p>You are signed up for an upcoming volunteer shift.</p>"
        "<ul>"
        f"<li><strong>Pantry:</strong> {pantry_name}</li>"
        f"<li><strong>Role:</strong> {role_title}</li>"
        f"<li><strong>When:</strong> {shift_window}</li>"
        f"<li><strong>Where:</strong> {location}</li>"
        "</ul>"
        "<p>Thank you for volunteering your time to help those in need! See you at your shift.</p>"
        "<p>Volunteer Managing Teams</p>"
    )


def _notification_result(
    *,
    ok: bool,
    code: str,
    message: str,
    recipient_email: str | None = None,
    subject: str | None = None,
    provider_response: Any | None = None,
) -> NotificationResult:
    return {
        "ok": ok,
        "provider": "resend",
        "code": code,
        "message": message,
        "recipient_email": recipient_email,
        "subject": subject,
        "provider_response": provider_response,
    }


def _send_resend_email(
    params: dict[str, Any],
    *,
    recipient_email: str,
    subject: str,
) -> NotificationResult:
    if not RESEND_API_KEY:
        return _notification_result(
            ok=False,
            code="RESEND_API_KEY_MISSING",
            message="Resend API key is not configured.",
            recipient_email=recipient_email,
            subject=subject,
        )

    try:
        import resend
    except ImportError as exc:
        return _notification_result(
            ok=False,
            code="RESEND_LIBRARY_MISSING",
            message=f"Resend library is not installed: {exc}",
            recipient_email=recipient_email,
            subject=subject,
        )

    resend.api_key = RESEND_API_KEY
    try:
        response = resend.Emails.send(params)
    except Exception as exc:
        return _notification_result(
            ok=False,
            code="RESEND_SEND_FAILED",
            message=f"Failed to send email via Resend: {exc}",
            recipient_email=recipient_email,
            subject=subject,
        )

    return _notification_result(
        ok=True,
        code="SIGNUP_CONFIRMATION_SENT",
        message="Signup confirmation email sent.",
        recipient_email=recipient_email,
        subject=subject,
        provider_response=response,
    )


def send_signup_confirmation(
    recipient: dict[str, Any],
    shift: dict[str, Any],
    pantry: dict[str, Any],
    role: dict[str, Any],
) -> NotificationResult:
    to_email = _normalized_text(recipient.get("email"), "")
    if not to_email:
        return _notification_result(
            ok=False,
            code="RECIPIENT_EMAIL_MISSING",
            message="Recipient email is missing.",
        )

    recipient_name = _normalized_text(recipient.get("full_name"), DEFAULT_RECIPIENT_NAME)
    pantry_name = _normalized_text(pantry.get("name"), DEFAULT_PANTRY_NAME)
    role_title = _normalized_text(role.get("role_title"), DEFAULT_ROLE_TITLE)
    location = _normalized_text(pantry.get("location_address"), DEFAULT_LOCATION)
    shift_name = _normalized_text(shift.get("shift_name"), DEFAULT_SHIFT_NAME)
    shift_window = _format_shift_window(shift)
    subject = f"Volunteer Signup confirmed: {shift_name}"

    if not RESEND_FROM_EMAIL:
        return _notification_result(
            ok=False,
            code="SENDER_EMAIL_MISSING",
            message="Resend sender email is not configured.",
            recipient_email=to_email,
            subject=subject,
        )

    params = {
        "from": RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "html": _build_signup_confirmation_html(
            recipient_name=recipient_name,
            pantry_name=pantry_name,
            role_title=role_title,
            shift_window=shift_window,
            location=location,
        ),
    }

    return _send_resend_email(
        params,
        recipient_email=to_email,
        subject=subject,
    )
