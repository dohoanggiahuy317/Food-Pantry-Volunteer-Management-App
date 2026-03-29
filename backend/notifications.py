from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from typing import Any
from urllib.parse import urljoin

from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer

LOGGER = logging.getLogger(__name__)
SIGNUP_ACTION_SALT = "signup-email-action"
EMAIL_ACTION_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 14


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_shift_window(shift: dict[str, Any]) -> str:
    start_time = _parse_iso_datetime(shift.get("start_time"))
    end_time = _parse_iso_datetime(shift.get("end_time"))
    if not start_time or not end_time:
        return "Time unavailable"
    return f"{start_time.strftime('%A, %B %d, %Y at %I:%M %p UTC')} to {end_time.strftime('%I:%M %p UTC')}"


def _app_base_url() -> str | None:
    raw = str(os.getenv("APP_BASE_URL", "")).strip()
    if not raw:
        return None
    return raw.rstrip("/") + "/"


def _dashboard_url() -> str | None:
    base_url = _app_base_url()
    if not base_url:
        return None
    return urljoin(base_url, "dashboard")


def _action_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=secret_key, salt=SIGNUP_ACTION_SALT)


def build_signup_action_url(signup_id: int, action: str, secret_key: str) -> str | None:
    base_url = _app_base_url()
    if not base_url:
        return None
    normalized_action = str(action).strip().upper()
    token = _action_serializer(secret_key).dumps({"signup_id": int(signup_id), "action": normalized_action})
    return urljoin(base_url, f"email-actions/signups/{int(signup_id)}/{normalized_action.lower()}?token={token}")


def verify_signup_action_token(signup_id: int, action: str, token: str, secret_key: str) -> bool:
    try:
        payload = _action_serializer(secret_key).loads(token, max_age=EMAIL_ACTION_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, BadTimeSignature):
        return False
    return int(payload.get("signup_id", 0)) == int(signup_id) and str(payload.get("action", "")).upper() == str(action).upper()


def _send_resend_email(payload: dict[str, Any]) -> bool:
    api_key = str(os.getenv("RESEND_API_KEY", "")).strip()
    if not api_key:
        return False
    try:
        import resend
    except ImportError:
        LOGGER.warning("Resend SDK is not installed; skipping notification delivery")
        return False

    resend.api_key = api_key
    try:
        resend.Emails.send(payload)
        return True
    except Exception as exc:
        LOGGER.warning("Resend notification failed: %s", exc)
        return False


def _compose_links_text(confirm_url: str | None, cancel_url: str | None, manage_url: str | None) -> tuple[str, str]:
    text_lines: list[str] = []
    html_parts: list[str] = []
    if confirm_url:
        text_lines.append(f"Confirm: {confirm_url}")
        html_parts.append(f'<li><a href="{confirm_url}">Confirm</a></li>')
    if cancel_url:
        text_lines.append(f"Cancel: {cancel_url}")
        html_parts.append(f'<li><a href="{cancel_url}">Cancel</a></li>')
    if manage_url:
        text_lines.append(f"Manage signup: {manage_url}")
        html_parts.append(f'<li><a href="{manage_url}">Manage signup</a></li>')
    return "\n".join(text_lines), ("<ul>" + "".join(html_parts) + "</ul>") if html_parts else ""


def send_initial_signup_confirmation(
    recipient: dict[str, Any],
    shift: dict[str, Any],
    pantry: dict[str, Any],
    role: dict[str, Any],
    confirm_url: str | None,
    cancel_url: str | None,
    manage_url: str | None = None,
) -> bool:
    from_email = str(os.getenv("RESEND_FROM_EMAIL", "")).strip()
    to_email = str(recipient.get("email") or "").strip()
    if not from_email or not to_email:
        return False

    shift_window = _format_shift_window(shift)
    pantry_name = str(pantry.get("name") or "Pantry").strip()
    role_title = str(role.get("role_title") or "Volunteer role").strip()
    location = str(pantry.get("location_address") or "Location unavailable").strip()
    recipient_name = str(recipient.get("full_name") or "Volunteer").strip()
    links_text, links_html = _compose_links_text(confirm_url, cancel_url, manage_url or _dashboard_url())

    text_body = "\n".join(
        [
            f"Hi {recipient_name},",
            "",
            "You are signed up for an upcoming volunteer shift.",
            "",
            f"Pantry: {pantry_name}",
            f"Role: {role_title}",
            f"When: {shift_window}",
            f"Where: {location}",
            "",
            links_text,
            "",
            "Volunteer Managing",
        ]
    )
    html_body = (
        f"<p>Hi {recipient_name},</p>"
        "<p>You are signed up for an upcoming volunteer shift.</p>"
        "<ul>"
        f"<li><strong>Pantry:</strong> {pantry_name}</li>"
        f"<li><strong>Role:</strong> {role_title}</li>"
        f"<li><strong>When:</strong> {shift_window}</li>"
        f"<li><strong>Where:</strong> {location}</li>"
        "</ul>"
        f"{links_html}"
        "<p>Volunteer Managing</p>"
    )
    return _send_resend_email(
        {
            "from": from_email,
            "to": [to_email],
            "subject": f"Signup confirmed: {str(shift.get('shift_name') or 'your volunteer shift').strip()}",
            "text": text_body,
            "html": html_body,
        }
    )


def send_advance_action_reminder(
    recipient: dict[str, Any],
    shift: dict[str, Any],
    pantry: dict[str, Any],
    role: dict[str, Any],
    confirm_url: str | None,
    cancel_url: str | None,
) -> bool:
    from_email = str(os.getenv("RESEND_FROM_EMAIL", "")).strip()
    to_email = str(recipient.get("email") or "").strip()
    if not from_email or not to_email:
        return False

    shift_window = _format_shift_window(shift)
    pantry_name = str(pantry.get("name") or "Pantry").strip()
    role_title = str(role.get("role_title") or "Volunteer role").strip()
    location = str(pantry.get("location_address") or "Location unavailable").strip()
    recipient_name = str(recipient.get("full_name") or "Volunteer").strip()
    links_text, links_html = _compose_links_text(confirm_url, cancel_url, None)

    text_body = "\n".join(
        [
            f"Hi {recipient_name},",
            "",
            "Your volunteer shift is coming up in about 24 hours. Please confirm or cancel your attendance.",
            "",
            f"Pantry: {pantry_name}",
            f"Role: {role_title}",
            f"When: {shift_window}",
            f"Where: {location}",
            "",
            links_text,
            "",
            "Volunteer Managing",
        ]
    )
    html_body = (
        f"<p>Hi {recipient_name},</p>"
        "<p>Your volunteer shift is coming up in about 24 hours. Please confirm or cancel your attendance.</p>"
        "<ul>"
        f"<li><strong>Pantry:</strong> {pantry_name}</li>"
        f"<li><strong>Role:</strong> {role_title}</li>"
        f"<li><strong>When:</strong> {shift_window}</li>"
        f"<li><strong>Where:</strong> {location}</li>"
        "</ul>"
        f"{links_html}"
        "<p>Volunteer Managing</p>"
    )
    return _send_resend_email(
        {
            "from": from_email,
            "to": [to_email],
            "subject": f"Reminder: confirm or cancel {str(shift.get('shift_name') or 'your volunteer shift').strip()}",
            "text": text_body,
            "html": html_body,
        }
    )
