from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from auth import AuthError
from backends.base import StoreBackend


GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
GOOGLE_OPENID_SCOPES = ["openid", "email", GOOGLE_CALENDAR_SCOPE]


def client_id() -> str:
    return str(os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()


def client_secret() -> str:
    return str(os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()


def configured() -> bool:
    return bool(client_id() and client_secret())


def redirect_uri(default_redirect_uri: str) -> str:
    return str(os.getenv("GOOGLE_OAUTH_REDIRECT_URI") or default_redirect_uri or "").strip()


def status_payload(store: StoreBackend, user: dict[str, Any]) -> dict[str, Any]:
    connection = store.get_google_calendar_connection(int(user.get("user_id")))
    scopes = str(connection.get("scopes_csv") or "").split() if connection and connection.get("scopes_csv") else []
    return {
        "configured": configured(),
        "connected": bool(connection),
        "google_email": connection.get("google_email") if connection else None,
        "google_subject": connection.get("google_subject") if connection else None,
        "scopes": scopes,
        "updated_at": connection.get("updated_at") if connection else None,
    }


def authorization_url(state: str, default_redirect_uri: str) -> str:
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": client_id(),
            "redirect_uri": redirect_uri(default_redirect_uri),
            "response_type": "code",
            "scope": " ".join(GOOGLE_OPENID_SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )


def http_json(
    method: str,
    url: str,
    *,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)

    payload_bytes: bytes | None = None
    if data is not None:
        if request_headers.get("Content-Type") == "application/x-www-form-urlencoded":
            payload_bytes = urlencode(data).encode("utf-8")
        else:
            request_headers.setdefault("Content-Type", "application/json")
            payload_bytes = json.dumps(data).encode("utf-8")

    outgoing_request = Request(url, data=payload_bytes, headers=request_headers, method=method.upper())
    try:
        with urlopen(outgoing_request, timeout=20) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        try:
            error_payload = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            error_payload = {"error": {"message": raw_body}}
        message = (
            error_payload.get("error_description")
            or (error_payload.get("error") or {}).get("message")
            or "Google request failed"
        )
        raise AuthError(message, 502, "GOOGLE_API_ERROR") from exc
    except URLError as exc:
        raise AuthError("Unable to reach Google Calendar services", 502, "GOOGLE_API_UNREACHABLE") from exc

    if not body:
        return {}
    parsed = json.loads(body)
    if isinstance(parsed, dict):
        return parsed
    raise AuthError("Google returned an unexpected response format", 502, "GOOGLE_API_INVALID_PAYLOAD")


def exchange_code_for_tokens(code: str, default_redirect_uri: str) -> dict[str, Any]:
    return http_json(
        "POST",
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id(),
            "client_secret": client_secret(),
            "redirect_uri": redirect_uri(default_redirect_uri),
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    return http_json(
        "POST",
        "https://oauth2.googleapis.com/token",
        data={
            "refresh_token": refresh_token,
            "client_id": client_id(),
            "client_secret": client_secret(),
            "grant_type": "refresh_token",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def fetch_user_info(access_token: str) -> dict[str, Any]:
    return http_json(
        "GET",
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )


def token_expiry(expires_in_seconds: Any) -> str | None:
    try:
        expires_in = int(expires_in_seconds)
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0, expires_in - 30))).isoformat().replace("+00:00", "Z")


def parse_iso_datetime_to_utc(value: Any) -> datetime | None:
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
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def access_token_for_user(store: StoreBackend, user_id: int) -> str:
    connection = store.get_google_calendar_connection(user_id)
    if not connection:
        raise AuthError("Google Calendar is not connected for this user", 409, "GOOGLE_CALENDAR_NOT_CONNECTED")

    expires_at = parse_iso_datetime_to_utc(connection.get("token_expires_at"))
    access_token = str(connection.get("access_token") or "").strip()
    refresh_token = str(connection.get("refresh_token") or "").strip()

    if access_token and expires_at and expires_at > datetime.now(timezone.utc):
        return access_token
    if not refresh_token:
        raise AuthError("Google Calendar connection is missing a refresh token", 409, "GOOGLE_CALENDAR_REFRESH_MISSING")

    refreshed = refresh_access_token(refresh_token)
    next_access_token = str(refreshed.get("access_token") or "").strip()
    if not next_access_token:
        raise AuthError("Google did not return a new access token", 502, "GOOGLE_CALENDAR_REFRESH_FAILED")

    store.upsert_google_calendar_connection(
        user_id,
        {
            "google_subject": connection.get("google_subject"),
            "google_email": connection.get("google_email"),
            "scopes_csv": str(refreshed.get("scope") or connection.get("scopes_csv") or "").strip(),
            "refresh_token": refresh_token,
            "access_token": next_access_token,
            "token_expires_at": token_expiry(refreshed.get("expires_in")),
        },
    )
    return next_access_token


def event_payload(
    signup: dict[str, Any],
    *,
    pending_confirmation_status: str,
    status_note: str | None = None,
) -> dict[str, Any]:
    pantry_name = str(signup.get("pantry_name") or "Pantry").strip()
    shift_name = str(signup.get("shift_name") or "Volunteer Shift").strip()
    role_title = str(signup.get("role_title") or "Volunteer").strip()
    pantry_location = str(signup.get("pantry_location") or "").strip()
    signup_status = str(signup.get("signup_status") or "CONFIRMED").strip().upper()
    summary_prefix = "[Needs Confirmation] " if signup_status == pending_confirmation_status else ""
    description_lines = [
        "Volunteer shift from Volunteer Management System",
        f"Pantry: {pantry_name}",
        f"Role: {role_title}",
        f"Signup status: {signup_status}",
    ]
    if pantry_location:
        description_lines.append(f"Location: {pantry_location}")
    if status_note:
        description_lines.append(status_note)

    return {
        "summary": f"{summary_prefix}{shift_name} ({role_title}) - {pantry_name}",
        "location": pantry_location or None,
        "description": "\n".join(description_lines),
        "start": {"dateTime": signup.get("start_time"), "timeZone": "UTC"},
        "end": {"dateTime": signup.get("end_time"), "timeZone": "UTC"},
    }


def create_event(
    store: StoreBackend,
    signup: dict[str, Any],
    *,
    pending_confirmation_status: str,
    status_note: str | None = None,
) -> dict[str, Any] | None:
    user_id = int(signup.get("user_id", 0))
    if not store.get_google_calendar_connection(user_id):
        return None
    access_token = access_token_for_user(store, user_id)
    created = http_json(
        "POST",
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        data=event_payload(signup, pending_confirmation_status=pending_confirmation_status, status_note=status_note),
        headers={"Authorization": f"Bearer {access_token}"},
    )
    event_id = str(created.get("id") or "").strip()
    if not event_id:
        raise AuthError("Google Calendar did not return an event id", 502, "GOOGLE_EVENT_ID_MISSING")
    store.upsert_google_calendar_event_link(
        int(signup.get("signup_id")),
        {
            "user_id": user_id,
            "calendar_id": "primary",
            "google_event_id": event_id,
        },
    )
    return created


def update_event(
    store: StoreBackend,
    signup: dict[str, Any],
    *,
    pending_confirmation_status: str,
    status_note: str | None = None,
    create_if_missing: bool = True,
) -> dict[str, Any] | None:
    user_id = int(signup.get("user_id", 0))
    if not store.get_google_calendar_connection(user_id):
        return None
    link = store.get_google_calendar_event_link(int(signup.get("signup_id")))
    if not link:
        return create_event(
            store,
            signup,
            pending_confirmation_status=pending_confirmation_status,
            status_note=status_note,
        ) if create_if_missing else None

    access_token = access_token_for_user(store, user_id)
    event_id = str(link.get("google_event_id") or "").strip()
    if not event_id:
        return create_event(
            store,
            signup,
            pending_confirmation_status=pending_confirmation_status,
            status_note=status_note,
        ) if create_if_missing else None

    try:
        return http_json(
            "PATCH",
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{quote(event_id, safe='')}",
            data=event_payload(signup, pending_confirmation_status=pending_confirmation_status, status_note=status_note),
            headers={"Authorization": f"Bearer {access_token}"},
        )
    except AuthError as error:
        if error.code == "GOOGLE_API_ERROR":
            store.delete_google_calendar_event_link(int(signup.get("signup_id")))
            return create_event(
                store,
                signup,
                pending_confirmation_status=pending_confirmation_status,
                status_note=status_note,
            ) if create_if_missing else None
        raise


def delete_event_for_signup_id(store: StoreBackend, signup_id: int, user_id: int | None = None) -> None:
    link = store.get_google_calendar_event_link(signup_id)
    if not link:
        return
    resolved_user_id = int(user_id or link.get("user_id") or 0)
    if resolved_user_id <= 0:
        store.delete_google_calendar_event_link(signup_id)
        return

    if not store.get_google_calendar_connection(resolved_user_id):
        store.delete_google_calendar_event_link(signup_id)
        return

    access_token = access_token_for_user(store, resolved_user_id)
    event_id = str(link.get("google_event_id") or "").strip()
    if event_id:
        try:
            http_json(
                "DELETE",
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{quote(event_id, safe='')}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except AuthError:
            pass
    store.delete_google_calendar_event_link(signup_id)
