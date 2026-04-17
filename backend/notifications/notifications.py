from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
DEFAULT_SHIFT_ACTION = "Please review the latest details in My Shifts."
DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_SUBSCRIBER_ACTION = "Open the app to review the pantry and sign up if a role fits your schedule."


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


def _normalized_role_titles(signups: list[dict[str, Any]]) -> str:
    seen: set[str] = set()
    titles: list[str] = []
    for signup in signups:
        role_title = _normalized_text(signup.get("role_title"), DEFAULT_ROLE_TITLE)
        if role_title in seen:
            continue
        seen.add(role_title)
        titles.append(role_title)
    if not titles:
        return DEFAULT_ROLE_TITLE
    return ", ".join(titles)


def _normalized_role_titles_from_roles(roles: list[dict[str, Any]]) -> str:
    seen: set[str] = set()
    titles: list[str] = []
    for role in roles:
        role_title = _normalized_text(role.get("role_title"), "")
        if not role_title or role_title in seen:
            continue
        seen.add(role_title)
        titles.append(role_title)
    if not titles:
        return "Roles will be announced soon"
    return ", ".join(titles)


def _resolved_timezone_name(value: Any) -> str:
    timezone_name = str(value or "").strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(timezone_name)
        return timezone_name
    except ZoneInfoNotFoundError:
        return DEFAULT_TIMEZONE


def _format_shift_window(shift: dict[str, Any], timezone_name: str | None = None) -> str:
    start_time = _parse_iso_datetime_to_utc(shift.get("start_time"))
    end_time = _parse_iso_datetime_to_utc(shift.get("end_time"))
    if not start_time or not end_time:
        return TIME_UNAVAILABLE_LABEL
    resolved_timezone = ZoneInfo(_resolved_timezone_name(timezone_name))
    local_start = start_time.astimezone(resolved_timezone)
    local_end = end_time.astimezone(resolved_timezone)
    start_timezone_label = local_start.tzname() or _resolved_timezone_name(timezone_name)
    end_timezone_label = local_end.tzname() or _resolved_timezone_name(timezone_name)
    timezone_label = start_timezone_label if start_timezone_label == end_timezone_label else f"{start_timezone_label} / {end_timezone_label}"

    if local_start.date() == local_end.date():
        return (
            f"{local_start.strftime('%A, %B %d, %Y at %I:%M %p')} "
            f"- {local_end.strftime('%I:%M %p')} {timezone_label}"
        )

    return (
        f"{local_start.strftime('%A, %B %d, %Y at %I:%M %p')} "
        f"- {local_end.strftime('%A, %B %d, %Y at %I:%M %p')} {timezone_label}"
    )


def _build_email_html(
    recipient_name: str,
    intro: str,
    details: list[tuple[str, str]],
    outro: str,
) -> str:
    detail_items = "".join(
        f"<li><strong>{label}:</strong> {value}</li>"
        for label, value in details
    )
    return (
        f"<p>Hi {recipient_name},</p>"
        f"<p>{intro}</p>"
        "<ul>"
        f"{detail_items}"
        "</ul>"
        f"<p>{outro}</p>"
        "<p>Volunteer Managing Teams</p>"
    )


def _weekday_labels(weekdays: list[Any]) -> str:
    weekday_lookup = {
        "MO": "Mon",
        "TU": "Tue",
        "WE": "Wed",
        "TH": "Thu",
        "FR": "Fri",
        "SA": "Sat",
        "SU": "Sun",
    }
    labels = [weekday_lookup.get(str(code or "").upper(), str(code or "").upper()) for code in weekdays if code]
    return ", ".join(labels)


def _format_recurrence_summary(recurrence: dict[str, Any]) -> str:
    interval_weeks = int(recurrence.get("interval_weeks", 1) or 1)
    every_text = "every week" if interval_weeks == 1 else f"every {interval_weeks} weeks"
    weekdays_text = _weekday_labels(list(recurrence.get("weekdays") or [])) or "selected days"
    end_mode = str(recurrence.get("end_mode") or "").upper()
    if end_mode == "UNTIL" and recurrence.get("until_date"):
        end_text = f"until {recurrence['until_date']}"
    elif recurrence.get("occurrence_count") is not None:
        end_text = f"for {int(recurrence['occurrence_count'])} occurrence(s)"
    else:
        end_text = "for a recurring series"
    return f"{every_text} on {weekdays_text}, {end_text}"


def _format_occurrence_preview(occurrences: list[dict[str, Any]], timezone_name: str | None) -> str:
    preview_items = []
    for occurrence in occurrences[:3]:
        preview_items.append(_format_shift_window(occurrence, timezone_name))
    return " | ".join(item for item in preview_items if item) or TIME_UNAVAILABLE_LABEL


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
    success_code: str,
    success_message: str,
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
        code=success_code,
        message=success_message,
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
    shift_window = _format_shift_window(shift, recipient.get("timezone"))
    subject = f"Volunteer signup confirmed: {shift_name}"

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
        "html": _build_email_html(
            recipient_name=recipient_name,
            intro="Your volunteer signup is confirmed.",
            details=[
                ("Pantry", pantry_name),
                ("Role", role_title),
                ("When", shift_window),
                ("Where", location),
            ],
            outro="Thank you for volunteering your time to help those in need. We will see you at your shift.",
        ),
    }

    return _send_resend_email(
        params,
        recipient_email=to_email,
        subject=subject,
        success_code="SIGNUP_CONFIRMATION_SENT",
        success_message="Signup confirmation email sent.",
    )


def send_shift_update_notification(
    recipient: dict[str, Any],
    shift: dict[str, Any],
    pantry: dict[str, Any],
    signups: list[dict[str, Any]],
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
    role_titles = _normalized_role_titles(signups)
    location = _normalized_text(pantry.get("location_address"), DEFAULT_LOCATION)
    shift_name = _normalized_text(shift.get("shift_name"), DEFAULT_SHIFT_NAME)
    shift_window = _format_shift_window(shift, recipient.get("timezone"))
    subject = f"Shift updated: action needed for {shift_name}"

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
        "html": _build_email_html(
            recipient_name=recipient_name,
            intro="Your volunteer shift details changed. Please review the updated details below and reconfirm from My Shifts.",
            details=[
                ("Pantry", pantry_name),
                ("Role", role_titles),
                ("When", shift_window),
                ("Where", location),
            ],
            outro=DEFAULT_SHIFT_ACTION,
        ),
    }

    return _send_resend_email(
        params,
        recipient_email=to_email,
        subject=subject,
        success_code="SHIFT_UPDATE_NOTIFICATION_SENT",
        success_message="Shift update notification email sent.",
    )


def send_shift_cancellation_notification(
    recipient: dict[str, Any],
    shift: dict[str, Any],
    pantry: dict[str, Any],
    signups: list[dict[str, Any]],
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
    role_titles = _normalized_role_titles(signups)
    location = _normalized_text(pantry.get("location_address"), DEFAULT_LOCATION)
    shift_name = _normalized_text(shift.get("shift_name"), DEFAULT_SHIFT_NAME)
    shift_window = _format_shift_window(shift, recipient.get("timezone"))
    subject = f"Shift cancelled: {shift_name}"

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
        "html": _build_email_html(
            recipient_name=recipient_name,
            intro="Your volunteer shift has been cancelled. No attendance is expected for this shift.",
            details=[
                ("Pantry", pantry_name),
                ("Role", role_titles),
                ("When", shift_window),
                ("Where", location),
            ],
            outro="Thank you for your flexibility and for volunteering with us.",
        ),
    }

    return _send_resend_email(
        params,
        recipient_email=to_email,
        subject=subject,
        success_code="SHIFT_CANCELLATION_NOTIFICATION_SENT",
        success_message="Shift cancellation notification email sent.",
    )


def send_new_shift_subscriber_notification(
    recipient: dict[str, Any],
    pantry: dict[str, Any],
    shift: dict[str, Any],
    roles: list[dict[str, Any]],
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
    location = _normalized_text(pantry.get("location_address"), DEFAULT_LOCATION)
    shift_name = _normalized_text(shift.get("shift_name"), DEFAULT_SHIFT_NAME)
    shift_window = _format_shift_window(shift, recipient.get("timezone"))
    role_titles = _normalized_role_titles_from_roles(roles)
    subject = f"New volunteer shift: {shift_name}"

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
        "html": _build_email_html(
            recipient_name=recipient_name,
            intro="A pantry you subscribed to just posted a new volunteer shift.",
            details=[
                ("Pantry", pantry_name),
                ("Shift", shift_name),
                ("When", shift_window),
                ("Where", location),
                ("Roles", role_titles),
            ],
            outro=DEFAULT_SUBSCRIBER_ACTION,
        ),
    }

    return _send_resend_email(
        params,
        recipient_email=to_email,
        subject=subject,
        success_code="NEW_SHIFT_SUBSCRIBER_NOTIFICATION_SENT",
        success_message="New shift subscriber notification email sent.",
    )


def send_new_shift_series_subscriber_notification(
    recipient: dict[str, Any],
    pantry: dict[str, Any],
    shift: dict[str, Any],
    roles: list[dict[str, Any]],
    recurrence: dict[str, Any],
    created_shift_count: int,
    preview_occurrences: list[dict[str, Any]],
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
    location = _normalized_text(pantry.get("location_address"), DEFAULT_LOCATION)
    shift_name = _normalized_text(shift.get("shift_name"), DEFAULT_SHIFT_NAME)
    role_titles = _normalized_role_titles_from_roles(roles)
    recurrence_summary = _format_recurrence_summary(recurrence)
    occurrence_preview = _format_occurrence_preview(preview_occurrences, recipient.get("timezone"))
    subject = f"New recurring volunteer shifts: {shift_name}"

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
        "html": _build_email_html(
            recipient_name=recipient_name,
            intro="A pantry you subscribed to just posted a new recurring volunteer shift series.",
            details=[
                ("Pantry", pantry_name),
                ("Shift", shift_name),
                ("Pattern", recurrence_summary),
                ("Occurrences Created", str(int(created_shift_count))),
                ("Upcoming Preview", occurrence_preview),
                ("Where", location),
                ("Roles", role_titles),
            ],
            outro=DEFAULT_SUBSCRIBER_ACTION,
        ),
    }

    return _send_resend_email(
        params,
        recipient_email=to_email,
        subject=subject,
        success_code="NEW_SHIFT_SERIES_SUBSCRIBER_NOTIFICATION_SENT",
        success_message="New recurring shift subscriber summary email sent.",
    )
