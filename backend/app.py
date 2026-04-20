from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request, session
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from auth import AuthError, create_auth_service
from backends.base import StoreBackend
from backends.factory import create_backend
from notifications import (
    send_new_shift_series_subscriber_notification,
    send_new_shift_subscriber_notification,
    send_shift_cancellation_notification,
    send_shift_update_notification,
    send_signup_confirmation,
)

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_csv(name: str) -> list[str]:
    raw_value = str(os.getenv(name, "") or "")
    return [item.strip() for item in raw_value.split(",") if item.strip()]


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"

app = Flask(
    __name__,
    static_folder=str(ROOT_DIR / "frontend" / "static"),
    template_folder=str(ROOT_DIR / "frontend" / "templates"),
)
flask_secret_key = str(os.getenv("FLASK_SECRET_KEY") or "").strip()
if flask_secret_key:
    app.config["SECRET_KEY"] = flask_secret_key
elif IS_PRODUCTION:
    raise RuntimeError("Missing FLASK_SECRET_KEY for production")
else:
    app.config["SECRET_KEY"] = "volunteer-managing-dev-secret"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = env_flag("SESSION_COOKIE_SECURE", IS_PRODUCTION)
app.config["PREFERRED_URL_SCHEME"] = "https" if env_flag("PREFERRED_URL_SCHEME_HTTPS", IS_PRODUCTION) else "http"

if env_flag("TRUST_REVERSE_PROXY", IS_PRODUCTION):
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=int(os.getenv("PROXY_FIX_X_FOR", "1")),
        x_proto=int(os.getenv("PROXY_FIX_X_PROTO", "1")),
        x_host=int(os.getenv("PROXY_FIX_X_HOST", "1")),
        x_port=int(os.getenv("PROXY_FIX_X_PORT", "1")),
    )

cors_allowed_origins = env_csv("CORS_ALLOWED_ORIGINS")
if cors_allowed_origins:
    CORS(app, resources={r"/api/*": {"origins": cors_allowed_origins}}, supports_credentials=True)
elif not IS_PRODUCTION:
    CORS(app, resources={r"/*": {"origins": "*"}})

backend: StoreBackend = create_backend()
auth_service = create_auth_service()

ATTENDANCE_STATUSES = {"SHOW_UP", "NO_SHOW"}
SIGNUP_STATUS_PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
SIGNUP_STATUS_CONFIRMED = "CONFIRMED"
SIGNUP_STATUS_WAITLISTED = "WAITLISTED"
SIGNUP_STATUS_CANCELLED = "CANCELLED"
PAST_SHIFT_LOCK_CODE = "PAST_SHIFT_LOCKED"
ACTIVE_SIGNUP_STATUSES = {SIGNUP_STATUS_CONFIRMED, "SHOW_UP", "NO_SHOW"}
LEAD_VISIBLE_SIGNUP_STATUSES = ACTIVE_SIGNUP_STATUSES
RESERVATION_WINDOW_HOURS = 48
MAX_SIGNUPS_PER_24_HOURS = 5
SIGNUP_RATE_LIMIT_WINDOW = timedelta(hours=24)
ADMIN_ROLE_NAME = "ADMIN"
SUPER_ADMIN_ROLE_NAME = "SUPER_ADMIN"
PROTECTED_SUPER_ADMIN_USER_ID = 1
RECURRING_FREQUENCY_WEEKLY = "WEEKLY"
RECURRING_END_MODE_COUNT = "COUNT"
RECURRING_END_MODE_UNTIL = "UNTIL"
WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
WEEKDAY_TO_INDEX = {code: index for index, code in enumerate(WEEKDAY_CODES)}
INDEX_TO_WEEKDAY = {index: code for code, index in WEEKDAY_TO_INDEX.items()}
MAX_RECURRING_OCCURRENCES = 260
AUTH_EXEMPT_API_PATHS = {
    "/api/auth/config",
    "/api/auth/login/google",
    "/api/auth/signup/google",
    "/api/auth/login/memory",
    "/api/auth/logout",
    "/api/me",
}


@app.before_request
def set_current_user() -> None:
    session_user_id = session.get("user_id")
    g.current_user_id = int(session_user_id) if session_user_id is not None else None

    if request.method == "OPTIONS":
        return

    path = request.path
    if not path.startswith("/api/"):
        return
    if path.startswith("/api/public/") or path in AUTH_EXEMPT_API_PATHS:
        return
    if g.current_user_id is None:
        return jsonify({"error": "Authentication required"}), 401


def find_user_by_id(user_id: int) -> dict[str, Any] | None:
    return backend.get_user_by_id(user_id)


def get_user_roles(user_id: int) -> list[str]:
    return backend.get_user_roles(user_id)


def user_has_role(user_id: int, role_name: str) -> bool:
    return role_name in get_user_roles(user_id)


def is_super_admin(user_id: int) -> bool:
    return user_has_role(user_id, SUPER_ADMIN_ROLE_NAME)


def is_admin_capable(user_id: int) -> bool:
    return is_super_admin(user_id) or user_has_role(user_id, ADMIN_ROLE_NAME)


def is_protected_super_admin_user_id(user_id: int) -> bool:
    return int(user_id) == PROTECTED_SUPER_ADMIN_USER_ID


def current_user() -> dict[str, Any] | None:
    user_id = getattr(g, "current_user_id", None)
    if user_id is None:
        return None
    user = find_user_by_id(user_id)
    if not user:
        return None
    return sync_user_timezone_from_request(user)


def normalized_timezone_name(value: Any) -> str | None:
    timezone_name = str(value or "").strip()
    if not timezone_name:
        return None
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return None
    return timezone_name


def sync_user_timezone_from_request(user: dict[str, Any]) -> dict[str, Any]:
    request_timezone = normalized_timezone_name(request.headers.get("X-Client-Timezone"))
    if not request_timezone:
        return user
    if str(user.get("timezone") or "").strip() == request_timezone:
        return user

    try:
        updated = backend.update_user(int(user.get("user_id")), {"timezone": request_timezone})
    except ValueError:
        return user
    return updated or user


def serialize_user_for_client(user: dict[str, Any] | None, include_roles: bool = False) -> dict[str, Any] | None:
    if not user:
        return None

    linked_auth_provider = user.get("auth_provider") or ("memory" if auth_service.mode == "memory" else None)
    payload = {
        "user_id": user.get("user_id"),
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "phone_number": user.get("phone_number"),
        "timezone": user.get("timezone"),
        "auth_mode": auth_service.mode,
        "auth_provider": linked_auth_provider,
        "auth_uid": user.get("auth_uid"),
        "email_change_supported": auth_service.mode == "firebase" and linked_auth_provider == "firebase",
        "attendance_score": int(user.get("attendance_score", 100)),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
    }
    if include_roles:
        payload["roles"] = get_user_roles(int(user.get("user_id")))
    return payload


def login_user_session(user: dict[str, Any]) -> None:
    session["user_id"] = int(user.get("user_id"))
    session.permanent = True


def logout_user_session() -> None:
    session.pop("user_id", None)


def normalize_email_address(value: Any) -> str:
    return str(value or "").strip().lower()


def is_valid_email_address(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value))


def json_auth_error(error: AuthError) -> tuple[Any, int]:
    payload = {"error": error.message}
    if error.code:
        payload["code"] = error.code
    return jsonify(payload), error.status_code


def update_user_or_409(user_id: int, payload: dict[str, Any], conflict_message: str | None = None) -> dict[str, Any]:
    try:
        updated = backend.update_user(user_id, payload)
    except ValueError as error:
        raise AuthError(conflict_message or str(error), 409, "ACCOUNT_CONFLICT") from error
    if not updated:
        raise AuthError("User not found", 404, "USER_NOT_FOUND")
    return updated


def get_role_name_map() -> dict[int, str]:
    return {
        int(role.get("role_id")): str(role.get("role_name"))
        for role in backend.list_roles()
        if role.get("role_id") is not None and role.get("role_name")
    }


def sync_firebase_user_identity(identity: Any) -> dict[str, Any] | None:
    user = backend.get_user_by_auth_uid(identity.uid)
    if user:
        conflicting_user = backend.get_user_by_email(identity.email)
        if conflicting_user and int(conflicting_user.get("user_id")) != int(user.get("user_id")):
            raise AuthError(
                "This email is already associated with another account. Contact an administrator before signing in.",
                409,
                "AUTH_EMAIL_CONFLICT",
            )

        updates: dict[str, Any] = {}
        if user.get("email") != identity.email:
            updates["email"] = identity.email
        if user.get("auth_provider") != identity.provider:
            updates["auth_provider"] = identity.provider
        if user.get("auth_uid") != identity.uid:
            updates["auth_uid"] = identity.uid

        if updates:
            return update_user_or_409(
                int(user.get("user_id")),
                updates,
                "Unable to sync your Firebase account because the new email is already in use.",
            )
        return user

    user = backend.get_user_by_email(identity.email)
    if not user:
        return None

    updates = {}
    if user.get("email") != identity.email:
        updates["email"] = identity.email
    if user.get("auth_provider") != identity.provider:
        updates["auth_provider"] = identity.provider
    if user.get("auth_uid") != identity.uid:
        updates["auth_uid"] = identity.uid

    if updates:
        return update_user_or_409(
            int(user.get("user_id")),
            updates,
            "Unable to link this Firebase account because it is already associated with another user.",
        )
    return user


def delete_current_user_account_with_identity(user: dict[str, Any], payload: dict[str, Any]) -> tuple[Any, int]:
    user_id = int(user.get("user_id"))
    if is_protected_super_admin_user_id(user_id):
        return jsonify({"error": "The protected super admin account cannot delete itself"}), 403

    linked_auth_provider = str(user.get("auth_provider") or "").strip()
    linked_auth_uid = str(user.get("auth_uid") or "").strip()

    if auth_service.mode == "firebase" and linked_auth_provider == "firebase" and linked_auth_uid:
        id_token = payload.get("id_token")
        try:
            identity = auth_service.verify_google_token(id_token)
        except AuthError as error:
            return json_auth_error(error)
        if identity.uid != linked_auth_uid:
            return jsonify({"error": "Reauthenticate with the same Google account before deleting this account"}), 403
        try:
            auth_service.delete_user(identity.uid)
        except AuthError as error:
            return json_auth_error(error)

    backend.delete_user(user_id)
    logout_user_session()
    return jsonify({"ok": True}), 200


def find_pantry_by_id(pantry_id: int) -> dict[str, Any] | None:
    return backend.get_pantry_by_id(pantry_id)


def pantries_for_current_user() -> list[dict[str, Any]]:
    """Pantries the current user leads (or all if admin-capable)."""
    user = current_user()
    if not user:
        return []

    user_id = int(user.get("user_id"))
    all_pantries = backend.list_pantries()

    if is_admin_capable(user_id):
        return all_pantries

    if user_has_role(user_id, "PANTRY_LEAD"):
        return [p for p in all_pantries if backend.is_pantry_lead(int(p.get("pantry_id")), user_id)]

    return []


def get_pantry_leads(pantry_id: int) -> list[dict[str, Any]]:
    return backend.get_pantry_leads(pantry_id)


def user_can_manage_pantry(pantry_id: int, user_id: int) -> bool:
    return is_admin_capable(user_id) or backend.is_pantry_lead(pantry_id, user_id)


def volunteer_user_required() -> tuple[dict[str, Any] | None, Any | None]:
    user = current_user()
    if not user:
        return None, (jsonify({"error": "Forbidden"}), 403)

    user_id = int(user.get("user_id"))
    if not user_has_role(user_id, "VOLUNTEER"):
        return None, (jsonify({"error": "Volunteer role required"}), 403)
    return user, None


def upcoming_shifts_for_pantry_preview(pantry_id: int, limit: int = 3) -> list[dict[str, Any]]:
    shifts = backend.list_non_expired_shifts_by_pantry(pantry_id, include_cancelled=False)
    serialized: list[dict[str, Any]] = []
    for shift in shifts:
        payload = attach_shift_recurrence_metadata(shift)
        payload["roles"] = get_shift_roles(int(shift.get("shift_id")), include_cancelled=False)
        serialized.append(payload)

    serialized.sort(
        key=lambda item: (
            parse_iso_datetime_to_utc(item.get("start_time")) or datetime.max.replace(tzinfo=timezone.utc),
            int(item.get("shift_id") or 0),
        )
    )
    return serialized[:limit]


def volunteer_pantry_payload(pantry: dict[str, Any], subscriber_pantry_ids: set[int]) -> dict[str, Any]:
    pantry_id = int(pantry.get("pantry_id"))
    preview_shifts = upcoming_shifts_for_pantry_preview(pantry_id, limit=3)
    payload = dict(pantry)
    payload["leads"] = get_pantry_leads(pantry_id)
    payload["is_subscribed"] = pantry_id in subscriber_pantry_ids
    payload["preview_shifts"] = preview_shifts
    payload["upcoming_shift_count"] = len(
        backend.list_non_expired_shifts_by_pantry(pantry_id, include_cancelled=False)
    )
    return payload


def get_shift_roles(shift_id: int, include_cancelled: bool = True) -> list[dict[str, Any]]:
    roles = backend.list_shift_roles(shift_id)
    if include_cancelled:
        return roles
    return [role for role in roles if str(role.get("status", "")).upper() != "CANCELLED"]


def get_shift_signups(shift_role_id: int) -> list[dict[str, Any]]:
    return backend.list_shift_signups(shift_role_id)


def serialize_signup_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return safe user fields for signup views."""
    if not user:
        return None
    return {
        "user_id": user.get("user_id"),
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "attendance_score": int(user.get("attendance_score", 100)),
    }


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
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_iso_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def localize_shift_datetime(value: Any, timezone_name: str) -> datetime | None:
    utc_value = parse_iso_datetime_to_utc(value)
    normalized_timezone = normalized_timezone_name(timezone_name)
    if not utc_value or not normalized_timezone:
        return None
    return utc_value.astimezone(ZoneInfo(normalized_timezone))


def local_date_for_shift(value: Any, timezone_name: str) -> date | None:
    local_value = localize_shift_datetime(value, timezone_name)
    return local_value.date() if local_value else None


def recurrence_for_client(series: dict[str, Any] | None) -> dict[str, Any] | None:
    if not series:
        return None
    weekdays_csv = str(series.get("weekdays_csv") or "")
    weekdays = [code for code in weekdays_csv.split(",") if code]
    return {
        "shift_series_id": series.get("shift_series_id"),
        "timezone": series.get("timezone"),
        "frequency": series.get("frequency", RECURRING_FREQUENCY_WEEKLY),
        "interval_weeks": int(series.get("interval_weeks", 1)),
        "weekdays": weekdays,
        "end_mode": series.get("end_mode"),
        "occurrence_count": series.get("occurrence_count"),
        "until_date": series.get("until_date"),
    }


def recurrence_for_shift_scope(shift: dict[str, Any], series: dict[str, Any] | None = None) -> dict[str, Any] | None:
    shift_series_id = shift.get("shift_series_id")
    if shift_series_id is None:
        return None

    resolved_series = series or backend.get_shift_series_by_id(int(shift_series_id))
    recurrence = recurrence_for_client(resolved_series)
    if not recurrence:
        return None

    if recurrence.get("end_mode") == RECURRING_END_MODE_COUNT and recurrence.get("occurrence_count") is not None:
        series_position = int(shift.get("series_position") or 1)
        recurrence["occurrence_count"] = max(1, int(recurrence["occurrence_count"]) - series_position + 1)
    return recurrence


def attach_shift_recurrence_metadata(shift: dict[str, Any], include_recurrence: bool = False) -> dict[str, Any]:
    payload = dict(shift)
    shift_series_id = payload.get("shift_series_id")
    payload["shift_series_id"] = int(shift_series_id) if shift_series_id is not None else None
    payload["series_position"] = int(payload.get("series_position")) if payload.get("series_position") is not None else None
    payload["is_recurring"] = payload["shift_series_id"] is not None
    if include_recurrence and payload["shift_series_id"] is not None:
        payload["recurrence"] = recurrence_for_shift_scope(payload)
    return payload


def normalize_recurrence_payload(payload: Any, start_time: str | None = None) -> dict[str, Any] | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("recurrence must be an object")

    timezone_name = normalized_timezone_name(payload.get("timezone"))
    if not timezone_name:
        raise ValueError("recurrence.timezone must be a valid IANA timezone")

    frequency = str(payload.get("frequency", RECURRING_FREQUENCY_WEEKLY)).strip().upper()
    if frequency != RECURRING_FREQUENCY_WEEKLY:
        raise ValueError("Only WEEKLY recurrence is supported")

    try:
        interval_weeks = int(payload.get("interval_weeks", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("recurrence.interval_weeks must be >= 1") from exc
    if interval_weeks < 1:
        raise ValueError("recurrence.interval_weeks must be >= 1")

    weekdays_raw = payload.get("weekdays")
    if not isinstance(weekdays_raw, list) or not weekdays_raw:
        raise ValueError("recurrence.weekdays must be a non-empty array")

    normalized_weekdays: list[str] = []
    seen_weekdays: set[str] = set()
    for raw_weekday in weekdays_raw:
        weekday = str(raw_weekday or "").strip().upper()
        if weekday not in WEEKDAY_TO_INDEX:
            raise ValueError("recurrence.weekdays contains an invalid weekday")
        if weekday in seen_weekdays:
            continue
        seen_weekdays.add(weekday)
        normalized_weekdays.append(weekday)
    normalized_weekdays.sort(key=lambda code: WEEKDAY_TO_INDEX[code])

    end_mode = str(payload.get("end_mode", "")).strip().upper()
    occurrence_count: int | None = None
    until_date: date | None = None
    if end_mode == RECURRING_END_MODE_COUNT:
        try:
            occurrence_count = int(payload.get("occurrence_count"))
        except (TypeError, ValueError) as exc:
            raise ValueError("recurrence.occurrence_count must be >= 1") from exc
        if occurrence_count < 1 or occurrence_count > MAX_RECURRING_OCCURRENCES:
            raise ValueError(f"recurrence.occurrence_count must be between 1 and {MAX_RECURRING_OCCURRENCES}")
    elif end_mode == RECURRING_END_MODE_UNTIL:
        until_date = parse_iso_date(payload.get("until_date"))
        if not until_date:
            raise ValueError("recurrence.until_date must be a valid ISO date")
    else:
        raise ValueError("recurrence.end_mode must be COUNT or UNTIL")

    if start_time:
        start_local = localize_shift_datetime(start_time, timezone_name)
        if not start_local:
            raise ValueError("Shift start time is invalid")
        expected_weekday = INDEX_TO_WEEKDAY[start_local.weekday()]
        if expected_weekday not in normalized_weekdays:
            raise ValueError("Selected recurrence weekdays must include the shift start weekday")
        if until_date and until_date < start_local.date():
            raise ValueError("recurrence.until_date must be on or after the first occurrence date")

    return {
        "timezone": timezone_name,
        "frequency": frequency,
        "interval_weeks": interval_weeks,
        "weekdays": normalized_weekdays,
        "weekdays_csv": ",".join(normalized_weekdays),
        "end_mode": end_mode,
        "occurrence_count": occurrence_count,
        "until_date": until_date.isoformat() if until_date else None,
    }


def generate_weekly_occurrences(
    start_time: str,
    end_time: str,
    recurrence: dict[str, Any],
) -> list[dict[str, str]]:
    timezone_name = recurrence["timezone"]
    tz = ZoneInfo(timezone_name)
    start_utc = parse_iso_datetime_to_utc(start_time)
    end_utc = parse_iso_datetime_to_utc(end_time)
    if not start_utc or not end_utc or end_utc <= start_utc:
        raise ValueError("Shift time range is invalid")

    start_local = start_utc.astimezone(tz)
    end_local = end_utc.astimezone(tz)
    duration = end_utc - start_utc
    anchor_date = start_local.date()
    anchor_week_start = anchor_date - timedelta(days=anchor_date.weekday())
    selected_weekdays = {WEEKDAY_TO_INDEX[code] for code in recurrence["weekdays"]}
    interval_weeks = int(recurrence["interval_weeks"])
    end_mode = recurrence["end_mode"]
    occurrence_target = int(recurrence["occurrence_count"]) if recurrence.get("occurrence_count") else None
    until_date = parse_iso_date(recurrence.get("until_date"))

    occurrences: list[dict[str, str]] = []
    candidate_date = anchor_date
    iteration_guard = 0
    while len(occurrences) < MAX_RECURRING_OCCURRENCES and iteration_guard < 3660:
        iteration_guard += 1
        if candidate_date >= anchor_date:
            candidate_week_start = candidate_date - timedelta(days=candidate_date.weekday())
            weeks_since_anchor = (candidate_week_start - anchor_week_start).days // 7
            if weeks_since_anchor >= 0 and weeks_since_anchor % interval_weeks == 0 and candidate_date.weekday() in selected_weekdays:
                local_occurrence_start = datetime(
                    candidate_date.year,
                    candidate_date.month,
                    candidate_date.day,
                    start_local.hour,
                    start_local.minute,
                    start_local.second,
                    start_local.microsecond,
                    tzinfo=tz,
                )
                local_occurrence_end = local_occurrence_start + duration
                if until_date and local_occurrence_start.date() > until_date:
                    break
                occurrences.append(
                    {
                        "start_time": local_occurrence_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "end_time": local_occurrence_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    }
                )
                if end_mode == RECURRING_END_MODE_COUNT and occurrence_target and len(occurrences) >= occurrence_target:
                    break

        candidate_date += timedelta(days=1)
        if end_mode == RECURRING_END_MODE_UNTIL and until_date and candidate_date > until_date:
            break

    if not occurrences:
        raise ValueError("Recurrence rule did not generate any occurrences")
    if end_mode == RECURRING_END_MODE_COUNT and occurrence_target and len(occurrences) != occurrence_target:
        raise ValueError("Recurrence rule could not generate the requested number of occurrences")
    return occurrences


def recurrence_payload_for_series_create(
    pantry_id: int,
    created_by: int,
    recurrence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pantry_id": pantry_id,
        "created_by": created_by,
        "timezone": recurrence["timezone"],
        "frequency": recurrence["frequency"],
        "interval_weeks": recurrence["interval_weeks"],
        "weekdays_csv": recurrence["weekdays_csv"],
        "end_mode": recurrence["end_mode"],
        "occurrence_count": recurrence.get("occurrence_count"),
        "until_date": recurrence.get("until_date"),
    }


def recurrence_signature(recurrence: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if not recurrence:
        return None
    return (
        recurrence.get("timezone"),
        recurrence.get("frequency"),
        int(recurrence.get("interval_weeks", 1)),
        tuple(recurrence.get("weekdays", [])),
        recurrence.get("end_mode"),
        recurrence.get("occurrence_count"),
        recurrence.get("until_date"),
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def signup_rate_limit_cooldown_ends_at(
    signup_rows: list[dict[str, Any]],
    now_utc: datetime | None = None,
) -> datetime | None:
    now_utc = now_utc or datetime.now(timezone.utc)
    window_start = now_utc - SIGNUP_RATE_LIMIT_WINDOW
    recent_signup_times = sorted(
        created_at
        for signup_row in signup_rows
        if (created_at := parse_iso_datetime_to_utc(signup_row.get("created_at"))) is not None
        and created_at > window_start
    )

    if len(recent_signup_times) < MAX_SIGNUPS_PER_24_HOURS:
        return None

    cooldown_anchor_index = len(recent_signup_times) - MAX_SIGNUPS_PER_24_HOURS
    return recent_signup_times[cooldown_anchor_index] + SIGNUP_RATE_LIMIT_WINDOW


def signup_row_blocks_overlap(signup_row: dict[str, Any], now_utc: datetime | None = None) -> bool:
    now_utc = now_utc or datetime.now(timezone.utc)
    signup_status = str(signup_row.get("signup_status", "")).upper()
    if signup_status in {SIGNUP_STATUS_CANCELLED, SIGNUP_STATUS_WAITLISTED}:
        return False

    if str(signup_row.get("shift_status", "")).upper() == "CANCELLED":
        return False
    if str(signup_row.get("role_status", "")).upper() == "CANCELLED":
        return False

    if signup_status in ACTIVE_SIGNUP_STATUSES:
        return True

    if signup_status != SIGNUP_STATUS_PENDING_CONFIRMATION:
        return False

    reservation_expires_at = parse_iso_datetime_to_utc(signup_row.get("reservation_expires_at"))
    return reservation_expires_at is not None and reservation_expires_at > now_utc


def signup_row_overlaps_shift(signup_row: dict[str, Any], shift: dict[str, Any], target_shift_role_id: int) -> bool:
    if int(signup_row.get("shift_role_id", 0)) == target_shift_role_id:
        return False

    existing_start = parse_iso_datetime_to_utc(signup_row.get("start_time"))
    existing_end = parse_iso_datetime_to_utc(signup_row.get("end_time"))
    current_start = parse_iso_datetime_to_utc(shift.get("start_time"))
    current_end = parse_iso_datetime_to_utc(shift.get("end_time"))

    if not existing_start or not existing_end or not current_start or not current_end:
        return False

    return existing_start < current_end and current_start < existing_end


def is_upcoming_shift(shift: dict[str, Any]) -> bool:
    start_time = parse_iso_datetime_to_utc(shift.get("start_time"))
    if not start_time:
        return False
    return start_time > datetime.now(timezone.utc)


def shift_has_started(shift: dict[str, Any]) -> bool:
    start_time = parse_iso_datetime_to_utc(shift.get("start_time"))
    if not start_time:
        return False
    return datetime.now(timezone.utc) >= start_time


def shift_has_ended(shift: dict[str, Any]) -> bool:
    end_time = parse_iso_datetime_to_utc(shift.get("end_time"))
    if not end_time:
        return False
    return datetime.now(timezone.utc) >= end_time


def past_shift_locked_response() -> tuple[Any, int]:
    return jsonify({"error": "Past shifts are locked", "code": PAST_SHIFT_LOCK_CODE}), 409


def ensure_shift_manager_permission(user_id: int, shift: dict[str, Any]) -> bool:
    if is_admin_capable(user_id):
        return True
    pantry_id = int(shift.get("pantry_id"))
    return backend.is_pantry_lead(pantry_id, user_id)


def should_include_cancelled_shift_data(user: dict[str, Any] | None, pantry_id: int) -> bool:
    if not user:
        return False
    user_id = int(user.get("user_id"))
    if is_admin_capable(user_id):
        return True
    return backend.is_pantry_lead(pantry_id, user_id)


def collect_shift_signups(shift_id: int) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for role in get_shift_roles(shift_id, include_cancelled=True):
        role_id = int(role.get("shift_role_id"))
        for signup in get_shift_signups(role_id):
            rows.append((signup, role))
    return rows


def recalculate_shift_role_capacity(shift_role_id: int) -> dict[str, Any] | None:
    role = backend.get_shift_role_by_id(shift_role_id)
    if not role:
        return None

    signups = backend.list_shift_signups(shift_role_id)
    occupied_count = 0
    now_utc = datetime.now(timezone.utc)
    for signup in signups:
        signup_status = str(signup.get("signup_status", "")).upper()
        reservation_expires_at = parse_iso_datetime_to_utc(signup.get("reservation_expires_at"))
        is_reserved_pending = (
            signup_status == SIGNUP_STATUS_PENDING_CONFIRMATION
            and reservation_expires_at is not None
            and reservation_expires_at > now_utc
        )
        if signup_status in ACTIVE_SIGNUP_STATUSES or is_reserved_pending:
            occupied_count += 1

    role_status = str(role.get("status", "OPEN")).upper()
    required_count = int(role.get("required_count", 0))
    if role_status == "CANCELLED":
        next_status = "CANCELLED"
    else:
        next_status = "FULL" if occupied_count >= required_count else "OPEN"

    updated = backend.update_shift_role(
        shift_role_id,
        {"filled_count": occupied_count, "status": next_status},
    )
    return updated


def recalculate_shift_capacities(shift_id: int) -> None:
    for role in get_shift_roles(shift_id, include_cancelled=True):
        recalculate_shift_role_capacity(int(role.get("shift_role_id")))


def affected_contacts_from_signups(signups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_user_ids: set[int] = set()
    contacts: list[dict[str, Any]] = []
    for signup in signups:
        user_id = int(signup.get("user_id"))
        if user_id in seen_user_ids:
            continue
        seen_user_ids.add(user_id)
        user = find_user_by_id(user_id)
        if not user:
            continue
        contacts.append(
            {
                "user_id": user.get("user_id"),
                "full_name": user.get("full_name"),
                "email": user.get("email"),
            }
        )
    return contacts


def affected_signup_ids(signups: list[dict[str, Any]]) -> set[int]:
    return {
        int(signup.get("signup_id"))
        for signup in signups
        if signup.get("signup_id") is not None
    }


def signups_for_notification_by_user(
    shift_id: int,
    signups: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    signup_ids = affected_signup_ids(signups)
    rows_by_user: dict[int, list[dict[str, Any]]] = {}
    for signup in signups:
        user_id = signup.get("user_id")
        if user_id is None:
            continue
        normalized_user_id = int(user_id)
        if normalized_user_id in rows_by_user:
            continue
        rows = [
            row
            for row in backend.list_signups_by_user(normalized_user_id)
            if int(row.get("shift_id", 0)) == shift_id and int(row.get("signup_id", 0)) in signup_ids
        ]
        if rows:
            rows_by_user[normalized_user_id] = rows
    return rows_by_user


def mark_shift_signups_pending(shift_id: int) -> dict[str, Any]:
    shift = backend.get_shift_by_id(shift_id)
    if not shift or not is_upcoming_shift(shift):
        return {"affected_signup_count": 0, "affected_volunteer_contacts": [], "affected_signups": []}

    reservation_expires_at = (datetime.now(timezone.utc) + timedelta(hours=RESERVATION_WINDOW_HOURS)).isoformat().replace("+00:00", "Z")
    changed_signups = backend.bulk_mark_shift_signups_pending(shift_id, reservation_expires_at)

    recalculate_shift_capacities(shift_id)
    contacts = affected_contacts_from_signups(changed_signups)
    return {
        "affected_signup_count": len(changed_signups),
        "affected_volunteer_contacts": contacts,
        "affected_signups": changed_signups,
    }


def send_signup_confirmation_if_configured(
    signup: dict[str, Any],
    recipient: dict[str, Any] | None,
    shift: dict[str, Any],
    shift_role: dict[str, Any],
) -> None:
    if str(signup.get("signup_status", "")).upper() != SIGNUP_STATUS_CONFIRMED:
        return
    if not recipient:
        return

    pantry_id = shift.get("pantry_id")
    if pantry_id is None:
        return

    pantry = find_pantry_by_id(int(pantry_id))
    if not pantry:
        return

    try:
        result = send_signup_confirmation(
            recipient=recipient,
            shift=shift,
            pantry=pantry,
            role=shift_role,
        )
        if not result["ok"]:
            app.logger.warning(
                "Signup confirmation not sent for signup_id=%s code=%s message=%s",
                signup.get("signup_id"),
                result["code"],
                result["message"],
            )
    except Exception:
        app.logger.exception("Failed to send signup confirmation for signup_id=%s", signup.get("signup_id"))


def send_shift_notifications_if_configured(
    *,
    notification_type: str,
    shift: dict[str, Any],
    signups: list[dict[str, Any]],
) -> None:
    if not signups:
        return

    pantry_id = shift.get("pantry_id")
    if pantry_id is None:
        return

    pantry = find_pantry_by_id(int(pantry_id))
    if not pantry:
        return

    rows_by_user = signups_for_notification_by_user(int(shift.get("shift_id")), signups)
    for user_id, signup_rows in rows_by_user.items():
        recipient = find_user_by_id(user_id)
        if not recipient:
            continue

        try:
            if notification_type == "cancel":
                result = send_shift_cancellation_notification(
                    recipient=recipient,
                    shift=shift,
                    pantry=pantry,
                    signups=signup_rows,
                )
            else:
                result = send_shift_update_notification(
                    recipient=recipient,
                    shift=shift,
                    pantry=pantry,
                    signups=signup_rows,
                )

            if not result["ok"]:
                app.logger.warning(
                    "Shift notification not sent for shift_id=%s user_id=%s code=%s message=%s",
                    shift.get("shift_id"),
                    user_id,
                    result["code"],
                    result["message"],
                )
        except Exception:
            app.logger.exception(
                "Failed to send %s notification for shift_id=%s user_id=%s",
                notification_type,
                shift.get("shift_id"),
                user_id,
            )


def send_new_shift_notifications_to_subscribers_if_configured(
    *,
    pantry: dict[str, Any],
    shift: dict[str, Any],
    roles: list[dict[str, Any]],
    recurrence: dict[str, Any] | None = None,
    created_shift_count: int = 1,
    preview_occurrences: list[dict[str, Any]] | None = None,
) -> None:
    pantry_id = pantry.get("pantry_id")
    if pantry_id is None:
        return

    subscribers = backend.list_pantry_subscribers(int(pantry_id))
    if not subscribers:
        return

    preview = preview_occurrences or [shift]
    for recipient in subscribers:
        try:
            if recurrence:
                result = send_new_shift_series_subscriber_notification(
                    recipient=recipient,
                    pantry=pantry,
                    shift=shift,
                    roles=roles,
                    recurrence=recurrence,
                    created_shift_count=created_shift_count,
                    preview_occurrences=preview,
                )
            else:
                result = send_new_shift_subscriber_notification(
                    recipient=recipient,
                    pantry=pantry,
                    shift=shift,
                    roles=roles,
                )

            if not result["ok"]:
                app.logger.warning(
                    "Subscriber notification not sent for pantry_id=%s user_id=%s code=%s message=%s",
                    pantry_id,
                    recipient.get("user_id"),
                    result["code"],
                    result["message"],
                )
        except Exception:
            app.logger.exception(
                "Failed to send subscriber notification for pantry_id=%s user_id=%s",
                pantry_id,
                recipient.get("user_id"),
            )


def normalize_shift_roles_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("roles must be an array")

    normalized_roles: list[dict[str, Any]] = []
    seen_role_ids: set[int] = set()
    for role_payload in payload:
        if not isinstance(role_payload, dict):
            raise ValueError("Each role must be an object")

        role_title = str(role_payload.get("role_title") or "").strip()
        if not role_title:
            raise ValueError("role_title is required")

        try:
            required_count = int(role_payload.get("required_count"))
        except (TypeError, ValueError) as exc:
            raise ValueError("required_count must be >= 1") from exc
        if required_count < 1:
            raise ValueError("required_count must be >= 1")

        normalized_role: dict[str, Any] = {
            "role_title": role_title,
            "required_count": required_count,
        }
        raw_role_id = role_payload.get("shift_role_id")
        if raw_role_id is not None:
            role_id = int(raw_role_id)
            if role_id in seen_role_ids:
                raise ValueError("Duplicate shift_role_id in roles payload")
            seen_role_ids.add(role_id)
            normalized_role["shift_role_id"] = role_id
        normalized_roles.append(normalized_role)

    if not normalized_roles:
        raise ValueError("Shift must include at least one role")
    return normalized_roles


def hydrate_shift_for_manager(
    shift_id: int,
    *,
    include_cancelled: bool = True,
    include_recurrence: bool = False,
) -> dict[str, Any] | None:
    shift = backend.get_shift_by_id(shift_id)
    if not shift:
        return None
    payload = attach_shift_recurrence_metadata(shift, include_recurrence=include_recurrence)
    payload["roles"] = get_shift_roles(shift_id, include_cancelled=include_cancelled)
    return payload


def create_shift_with_roles(
    *,
    pantry_id: int,
    created_by: int,
    shift_name: str,
    start_time: str,
    end_time: str,
    roles_payload: list[dict[str, Any]],
    status: str = "OPEN",
    shift_series_id: int | None = None,
    series_position: int | None = None,
) -> dict[str, Any]:
    shift = backend.create_shift(
        pantry_id=pantry_id,
        shift_name=shift_name,
        start_time=start_time,
        end_time=end_time,
        status=status,
        created_by=created_by,
        shift_series_id=shift_series_id,
        series_position=series_position,
    )
    for role_payload in roles_payload:
        backend.create_shift_role(
            shift_id=int(shift.get("shift_id")),
            role_title=role_payload["role_title"],
            required_count=int(role_payload["required_count"]),
        )
    return hydrate_shift_for_manager(int(shift.get("shift_id")), include_cancelled=True, include_recurrence=True) or shift


def empty_affected_summary() -> dict[str, Any]:
    return {
        "affected_signup_count": 0,
        "affected_volunteer_contacts": [],
        "affected_signups": [],
    }


def merge_affected_summary(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = {
        "affected_signup_count": int(current.get("affected_signup_count", 0)) + int(incoming.get("affected_signup_count", 0)),
        "affected_volunteer_contacts": [],
        "affected_signups": list(current.get("affected_signups", [])),
    }

    seen_contacts: set[str] = set()
    for contact in list(current.get("affected_volunteer_contacts", [])) + list(incoming.get("affected_volunteer_contacts", [])):
        email = str(contact.get("email") or "").strip().lower()
        if not email or email in seen_contacts:
            continue
        seen_contacts.add(email)
        merged["affected_volunteer_contacts"].append(contact)

    seen_signup_ids = {
        int(signup.get("signup_id"))
        for signup in merged["affected_signups"]
        if signup.get("signup_id") is not None
    }
    for signup in incoming.get("affected_signups", []):
        signup_id = signup.get("signup_id")
        normalized_signup_id = int(signup_id) if signup_id is not None else None
        if normalized_signup_id is not None and normalized_signup_id in seen_signup_ids:
            continue
        if normalized_signup_id is not None:
            seen_signup_ids.add(normalized_signup_id)
        merged["affected_signups"].append(signup)
    return merged


def apply_single_shift_update_with_roles(
    shift_id: int,
    shift_payload: dict[str, Any],
    roles_payload: list[dict[str, Any]],
) -> dict[str, Any] | None:
    updated = backend.replace_shift_and_roles(
        shift_id=shift_id,
        shift_payload=shift_payload,
        roles_payload=roles_payload,
    )
    if not updated:
        return None

    affected = mark_shift_signups_pending(shift_id)
    notification_signups = affected.pop("affected_signups", [])
    recalculate_shift_capacities(shift_id)
    response = hydrate_shift_for_manager(shift_id, include_cancelled=True, include_recurrence=True) or updated
    response.update(affected)
    if affected["affected_signup_count"] > 0:
        send_shift_notifications_if_configured(
            notification_type="update",
            shift=response,
            signups=notification_signups,
        )
    return response


def cancel_single_shift_for_manager(shift_id: int) -> dict[str, Any] | None:
    shift = backend.get_shift_by_id(shift_id)
    if not shift:
        return None

    previous_status = str(shift.get("status", "OPEN")).upper()
    updated_shift = backend.update_shift(shift_id, {"status": "CANCELLED"})
    if not updated_shift:
        return None

    affected = mark_shift_signups_pending(shift_id)
    notification_signups = affected.pop("affected_signups", [])
    recalculate_shift_capacities(shift_id)
    response = hydrate_shift_for_manager(shift_id, include_cancelled=True, include_recurrence=True) or updated_shift
    response.update(affected)
    if previous_status != "CANCELLED" and affected["affected_signup_count"] > 0:
        send_shift_notifications_if_configured(
            notification_type="cancel",
            shift=response,
            signups=notification_signups,
        )
    return response


def sorted_series_shifts(shift_series_id: int) -> list[dict[str, Any]]:
    shifts = backend.list_shifts_by_series(shift_series_id)
    return sorted(
        shifts,
        key=lambda item: (
            int(item.get("series_position")) if item.get("series_position") is not None else 999999,
            str(item.get("start_time") or ""),
            int(item.get("shift_id", 0)),
        ),
    )


def future_series_shifts_from(shift: dict[str, Any]) -> list[dict[str, Any]]:
    shift_series_id = shift.get("shift_series_id")
    if shift_series_id is None:
        return []
    current_shift_id = int(shift.get("shift_id"))
    current_position = int(shift.get("series_position") or 0)
    shifts = sorted_series_shifts(int(shift_series_id))
    if current_position:
        return [row for row in shifts if int(row.get("series_position") or 0) >= current_position]

    found_current = False
    selected: list[dict[str, Any]] = []
    for row in shifts:
        if int(row.get("shift_id", 0)) == current_shift_id:
            found_current = True
        if found_current:
            selected.append(row)
    return selected


def split_series_update_targets(
    *,
    current_shift: dict[str, Any],
    shift_payload: dict[str, Any],
    roles_payload: list[dict[str, Any]],
    recurrence: dict[str, Any] | None,
    actor_user_id: int,
) -> dict[str, Any]:
    existing_segment_recurrence = recurrence_for_shift_scope(current_shift)
    effective_recurrence = recurrence or existing_segment_recurrence
    if not effective_recurrence:
        raise ValueError("Recurring metadata is missing for this shift")

    current_start_time = shift_payload.get("start_time", current_shift.get("start_time"))
    current_end_time = shift_payload.get("end_time", current_shift.get("end_time"))
    occurrences = generate_weekly_occurrences(current_start_time, current_end_time, effective_recurrence)
    target_shifts = future_series_shifts_from(current_shift)
    target_series_id = int(current_shift.get("shift_series_id"))

    rule_changed = recurrence_signature(effective_recurrence) != recurrence_signature(existing_segment_recurrence)
    if rule_changed:
        new_series = backend.create_shift_series(
            recurrence_payload_for_series_create(
                pantry_id=int(current_shift.get("pantry_id")),
                created_by=actor_user_id,
                recurrence=effective_recurrence,
            )
        )
        target_series_id = int(new_series.get("shift_series_id"))

    summary = empty_affected_summary()
    paired_count = min(len(target_shifts), len(occurrences))
    cancelled_occurrence_count = 0
    created_occurrence_count = 0

    for index in range(paired_count):
        target_shift = target_shifts[index]
        occurrence = occurrences[index]
        paired_shift_payload = dict(shift_payload)
        paired_shift_payload["start_time"] = occurrence["start_time"]
        paired_shift_payload["end_time"] = occurrence["end_time"]
        paired_shift_payload["shift_series_id"] = target_series_id
        paired_shift_payload["series_position"] = index + 1 if rule_changed else int(target_shift.get("series_position") or (index + 1))
        updated = apply_single_shift_update_with_roles(int(target_shift.get("shift_id")), paired_shift_payload, roles_payload)
        if updated:
            summary = merge_affected_summary(summary, updated)

    for index in range(paired_count, len(target_shifts)):
        target_shift = target_shifts[index]
        cancelled = cancel_single_shift_for_manager(int(target_shift.get("shift_id")))
        if cancelled:
            summary = merge_affected_summary(summary, cancelled)
        cancelled_occurrence_count += 1

    for index in range(paired_count, len(occurrences)):
        occurrence = occurrences[index]
        create_shift_with_roles(
            pantry_id=int(current_shift.get("pantry_id")),
            created_by=actor_user_id,
            shift_name=shift_payload.get("shift_name", current_shift.get("shift_name")),
            start_time=occurrence["start_time"],
            end_time=occurrence["end_time"],
            status=str(shift_payload.get("status", current_shift.get("status", "OPEN"))).upper(),
            roles_payload=roles_payload,
            shift_series_id=target_series_id,
            series_position=index + 1,
        )
        created_occurrence_count += 1

    response = hydrate_shift_for_manager(int(current_shift.get("shift_id")), include_cancelled=True, include_recurrence=True) or dict(current_shift)
    response.update(summary)
    response["updated_occurrence_count"] = paired_count
    response["cancelled_occurrence_count"] = cancelled_occurrence_count
    response["created_occurrence_count"] = created_occurrence_count
    response["apply_scope"] = "future"
    return response


def cancel_future_series_from(shift: dict[str, Any]) -> dict[str, Any]:
    target_shifts = future_series_shifts_from(shift)
    summary = empty_affected_summary()
    cancelled_occurrence_count = 0
    for target_shift in target_shifts:
        cancelled = cancel_single_shift_for_manager(int(target_shift.get("shift_id")))
        if cancelled:
            summary = merge_affected_summary(summary, cancelled)
        cancelled_occurrence_count += 1

    response = hydrate_shift_for_manager(int(shift.get("shift_id")), include_cancelled=True, include_recurrence=True) or dict(shift)
    response.update(summary)
    response["cancelled_occurrence_count"] = cancelled_occurrence_count
    response["apply_scope"] = "future"
    return response


def expire_pending_signups_if_started(shift_id: int) -> int:
    expired = backend.expire_pending_signups(shift_id, utc_now_iso())
    if expired > 0:
        recalculate_shift_capacities(shift_id)
    return expired


def signup_reconfirm_availability(signup_row: dict[str, Any]) -> tuple[bool, str | None]:
    signup_status = str(signup_row.get("signup_status", "")).upper()
    if signup_status != SIGNUP_STATUS_PENDING_CONFIRMATION:
        return False, "SIGNUP_NOT_PENDING"

    shift_status = str(signup_row.get("shift_status", "")).upper()
    if shift_status == "CANCELLED":
        return False, "SHIFT_CANCELLED"

    role_status = str(signup_row.get("role_status", "")).upper()
    if role_status == "CANCELLED":
        return False, "ROLE_FULL_OR_UNAVAILABLE"

    start_time = parse_iso_datetime_to_utc(signup_row.get("start_time"))
    if start_time and datetime.now(timezone.utc) >= start_time:
        return False, "SHIFT_ALREADY_STARTED"

    reservation_expires_at = parse_iso_datetime_to_utc(signup_row.get("reservation_expires_at"))
    if reservation_expires_at and datetime.now(timezone.utc) >= reservation_expires_at:
        return False, "RESERVATION_EXPIRED"

    return True, None


def enrich_signup_rows_for_reconfirm(signups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in signups:
        row_copy = dict(row)
        can_reconfirm, reason = signup_reconfirm_availability(row_copy)
        row_copy["reconfirm_available"] = can_reconfirm
        row_copy["reconfirm_reason"] = reason
        enriched.append(row_copy)
    return enriched


def get_signup_shift_context(signup_id: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    signup = backend.get_signup_by_id(signup_id)
    if not signup:
        return None, None, None

    shift_role_id = int(signup.get("shift_role_id"))
    shift_role = backend.get_shift_role_by_id(shift_role_id)
    if not shift_role:
        return signup, None, None

    shift_id = int(shift_role.get("shift_id"))
    shift = backend.get_shift_by_id(shift_id)
    return signup, shift_role, shift


def check_attendance_marking_allowed(actor_user_id: int, shift: dict[str, Any]) -> tuple[bool, str | None]:
    is_admin = is_admin_capable(actor_user_id)
    pantry_id = int(shift.get("pantry_id"))
    is_lead_for_pantry = backend.is_pantry_lead(pantry_id, actor_user_id)
    if not is_admin and not is_lead_for_pantry:
        return False, "Forbidden"

    start_time = parse_iso_datetime_to_utc(shift.get("start_time"))
    end_time = parse_iso_datetime_to_utc(shift.get("end_time"))
    if not start_time or not end_time:
        return False, "Shift time is invalid"

    # TODO(dev): Re-enable attendance time-window enforcement before production.
    # now_utc = datetime.now(timezone.utc)
    # open_at = start_time - timedelta(minutes=15)
    # close_at = end_time + timedelta(hours=6)
    # if now_utc < open_at or now_utc > close_at:
    #     return False, "Attendance can only be marked from 15 minutes before start until 6 hours after shift end"

    return True, None


def set_attendance_status(signup_id: int, attendance_status: str, actor_user_id: int) -> tuple[dict[str, Any] | None, tuple[str, int] | None]:
    normalized_status = str(attendance_status or "").strip().upper()
    if normalized_status not in ATTENDANCE_STATUSES:
        return None, ("attendance_status must be SHOW_UP or NO_SHOW", 400)

    signup, shift_role, shift = get_signup_shift_context(signup_id)
    if not signup:
        return None, ("Not found", 404)
    if not shift_role or not shift:
        return None, ("Shift context not found", 404)

    allowed, error = check_attendance_marking_allowed(actor_user_id, shift)
    if not allowed:
        if error == "Forbidden":
            return None, (error, 403)
        return None, (error or "Attendance cannot be marked right now", 400)

    updated = backend.update_signup(signup_id, normalized_status)
    if not updated:
        return None, ("Not found", 404)

    updated["user"] = serialize_signup_user(find_user_by_id(int(updated.get("user_id"))))
    return updated, None


# ========== API ROUTES ==========

@app.get("/api/auth/config")
def get_auth_config() -> Any:
    return jsonify(auth_service.get_client_config())


@app.post("/api/auth/login/memory")
def login_memory() -> Any:
    if auth_service.mode != "memory":
        return jsonify({"error": "Memory login is disabled"}), 400

    payload = request.get_json(silent=True) or {}
    sample_account_id = str(payload.get("sample_account_id", "")).strip()
    if not sample_account_id:
        return jsonify({"error": "Missing sample_account_id"}), 400

    try:
        sample_account = auth_service.resolve_memory_account(sample_account_id)
    except AuthError as error:
        return json_auth_error(error)

    user = backend.get_user_by_email(sample_account.get("email", ""))
    if not user:
        return jsonify({"error": "Sample account is not mapped to a local user"}), 500

    login_user_session(user)
    return jsonify({"user": serialize_user_for_client(user, include_roles=True), "next": "app"})


@app.post("/api/auth/login/google")
def login_google() -> Any:
    if auth_service.mode != "firebase":
        return jsonify({"error": "Google login is disabled"}), 400

    payload = request.get_json(silent=True) or {}
    try:
        identity = auth_service.verify_google_token(payload.get("id_token"))
    except AuthError as error:
        return json_auth_error(error)

    try:
        user = sync_firebase_user_identity(identity)
    except AuthError as error:
        return json_auth_error(error)

    if not user:
        return jsonify(
            {
                "signup_required": True,
                "email": identity.email,
                "display_name": identity.display_name,
                "next": "signup",
            }
        )

    login_user_session(user)
    return jsonify({"user": serialize_user_for_client(user, include_roles=True), "next": "app"})


@app.post("/api/auth/signup/google")
def signup_google() -> Any:
    if auth_service.mode != "firebase":
        return jsonify({"error": "Google signup is disabled"}), 400

    payload = request.get_json(silent=True) or {}
    full_name = str(payload.get("full_name", "")).strip()
    phone_number = str(payload.get("phone_number", "")).strip()
    timezone_name = str(payload.get("timezone", "")).strip() or None
    if not full_name or not phone_number:
        return jsonify({"error": "Missing: full_name, phone_number"}), 400

    try:
        identity = auth_service.verify_google_token(payload.get("id_token"))
    except AuthError as error:
        return json_auth_error(error)

    if backend.get_user_by_email(identity.email):
        return jsonify({"error": "Email already exists"}), 409

    try:
        user = backend.create_user(
            full_name=full_name,
            email=identity.email,
            phone_number=phone_number,
            roles=["VOLUNTEER"],
            timezone=timezone_name,
            auth_provider=identity.provider,
            auth_uid=identity.uid,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 409

    login_user_session(user)
    return jsonify({"user": serialize_user_for_client(user, include_roles=True), "next": "app"}), 201


@app.post("/api/auth/logout")
def logout() -> Any:
    logout_user_session()
    return jsonify({"ok": True})


@app.get("/api/me")
def get_current_user() -> Any:
    """Get current logged-in user with roles."""
    user = current_user()
    if not user:
        return jsonify({"error": "No user"}), 401
    return jsonify(serialize_user_for_client(user, include_roles=True))


@app.patch("/api/me")
def update_current_user_profile() -> Any:
    user = current_user()
    if not user:
        return jsonify({"error": "No user"}), 401

    payload = request.get_json(silent=True) or {}
    updates: dict[str, Any] = {}

    if "full_name" in payload:
        full_name = str(payload.get("full_name", "")).strip()
        if not full_name:
            return jsonify({"error": "full_name cannot be empty"}), 400
        updates["full_name"] = full_name

    if "phone_number" in payload:
        phone_number = str(payload.get("phone_number", "")).strip()
        updates["phone_number"] = phone_number or None

    if "timezone" in payload:
        timezone_name = str(payload.get("timezone", "")).strip()
        updates["timezone"] = timezone_name or None

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    try:
        updated = backend.update_user(int(user.get("user_id")), updates)
    except ValueError as error:
        return jsonify({"error": str(error)}), 409

    if not updated:
        return jsonify({"error": "User not found"}), 404
    return jsonify(serialize_user_for_client(updated, include_roles=True))


@app.post("/api/me/email-change/prepare")
def prepare_email_change() -> Any:
    user = current_user()
    if not user:
        return jsonify({"error": "No user"}), 401
    if auth_service.mode != "firebase":
        return jsonify({"error": "Email changes through Firebase are unavailable in the current auth mode"}), 400
    if str(user.get("auth_provider") or "") != "firebase" or not str(user.get("auth_uid") or "").strip():
        return jsonify({"error": "This account is not linked to Firebase yet. Please sign in again with Google first."}), 409

    payload = request.get_json(silent=True) or {}
    new_email = normalize_email_address(payload.get("new_email"))
    if not new_email:
        return jsonify({"error": "new_email is required"}), 400
    if not is_valid_email_address(new_email):
        return jsonify({"error": "new_email must be a valid email address"}), 400
    if new_email == normalize_email_address(user.get("email")):
        return jsonify({"error": "New email must be different from the current email"}), 400

    existing = backend.get_user_by_email(new_email)
    if existing and int(existing.get("user_id")) != int(user.get("user_id")):
        return jsonify({"error": "That email is already associated with another account"}), 409

    return jsonify({"ok": True, "new_email": new_email})


@app.delete("/api/me")
def delete_current_user_account() -> Any:
    user = current_user()
    if not user:
        return jsonify({"error": "No user"}), 401

    payload = request.get_json(silent=True) or {}
    return delete_current_user_account_with_identity(user, payload)


@app.get("/api/users")
def list_users() -> Any:
    """List all users for admin-capable actors."""
    user = current_user()
    if not user or not is_admin_capable(int(user.get("user_id"))):
        return jsonify({"error": "Forbidden"}), 403

    role_filter = request.args.get("role")
    query = str(request.args.get("q", "")).strip().lower()
    users = backend.list_users(role_filter)
    if query:
        users = [
            candidate
            for candidate in users
            if query in str(candidate.get("full_name", "")).lower()
            or query in str(candidate.get("email", "")).lower()
        ]
    return jsonify([serialize_user_for_client(u, include_roles=True) for u in users])


@app.get("/api/users/<int:user_id>")
def get_user_profile(user_id: int) -> Any:
    user = current_user()
    if not user or not is_admin_capable(int(user.get("user_id"))):
        return jsonify({"error": "Forbidden"}), 403

    target_user = find_user_by_id(user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(serialize_user_for_client(target_user, include_roles=True))


@app.get("/api/users/<int:user_id>/signups")
def list_user_signups(user_id: int) -> Any:
    """List signups for a specific user (self or admin-capable actor)."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    current_user_id = int(user.get("user_id"))
    is_admin = is_admin_capable(current_user_id)
    if current_user_id != user_id and not is_admin:
        return jsonify({"error": "Forbidden"}), 403

    target_user = find_user_by_id(user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404

    signups = backend.list_signups_by_user(user_id)
    unique_shift_ids = {int(row.get("shift_id")) for row in signups}

    expired_any = False
    for shift_id in unique_shift_ids:
        expired_count = expire_pending_signups_if_started(shift_id)
        if expired_count > 0:
            expired_any = True

    if expired_any:
        signups = backend.list_signups_by_user(user_id)

    return jsonify(enrich_signup_rows_for_reconfirm(signups))


@app.get("/api/roles")
def list_roles() -> Any:
    """List all available roles."""
    return jsonify(backend.list_roles())


@app.post("/api/users")
def create_user() -> Any:
    """Create a new user (admin-capable actors only)."""
    user = current_user()
    if not user or not is_admin_capable(int(user.get("user_id"))):
        return jsonify({"error": "Forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    required = ["full_name", "email"]
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({"error": f"Missing: {', '.join(missing)}"}), 400

    requested_roles = [str(role_name).strip().upper() for role_name in payload.get("roles", []) if str(role_name).strip()]
    if len(requested_roles) > 1:
        return jsonify({"error": "Users can have only one role"}), 400
    if SUPER_ADMIN_ROLE_NAME in requested_roles:
        return jsonify({"error": "The SUPER_ADMIN role cannot be assigned through this endpoint"}), 403

    try:
        new_user = backend.create_user(
            full_name=payload["full_name"],
            email=payload["email"],
            phone_number=payload.get("phone_number"),
            roles=requested_roles,
            timezone=(str(payload.get("timezone", "")).strip() or None),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(serialize_user_for_client(new_user, include_roles=True)), 201


@app.patch("/api/users/<int:user_id>/roles")
def replace_user_roles(user_id: int) -> Any:
    actor = current_user()
    if not actor:
        return jsonify({"error": "Forbidden"}), 403

    actor_user_id = int(actor.get("user_id"))
    if not is_admin_capable(actor_user_id):
        return jsonify({"error": "Forbidden"}), 403

    target_user = find_user_by_id(user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404

    payload = request.get_json(silent=True) or {}
    role_ids = payload.get("role_ids")
    if not isinstance(role_ids, list):
        return jsonify({"error": "role_ids must be an array"}), 400
    if len(role_ids) != 1:
        return jsonify({"error": "Users can have only one editable role"}), 400

    requested_role_ids: list[int] = []
    seen_role_ids: set[int] = set()
    try:
        for raw_role_id in role_ids:
            normalized_role_id = int(raw_role_id)
            if normalized_role_id in seen_role_ids:
                continue
            seen_role_ids.add(normalized_role_id)
            requested_role_ids.append(normalized_role_id)
    except (TypeError, ValueError):
        return jsonify({"error": "role_ids must contain integers only"}), 400

    role_name_map = get_role_name_map()
    unknown_role_ids = [role_id for role_id in requested_role_ids if role_id not in role_name_map]
    if unknown_role_ids:
        return jsonify({"error": f"Unknown role ids: {', '.join(str(role_id) for role_id in unknown_role_ids)}"}), 400

    current_role_names = set(get_user_roles(user_id))
    requested_role_names = {role_name_map[role_id] for role_id in requested_role_ids}

    if is_protected_super_admin_user_id(user_id) or SUPER_ADMIN_ROLE_NAME in current_role_names:
        return jsonify({"error": "The protected super admin account cannot have its roles edited"}), 403
    if SUPER_ADMIN_ROLE_NAME in requested_role_names:
        return jsonify({"error": "The SUPER_ADMIN role cannot be assigned through this endpoint"}), 403

    removing_admin = ADMIN_ROLE_NAME in current_role_names and ADMIN_ROLE_NAME not in requested_role_names
    if removing_admin and user_id != actor_user_id and not is_super_admin(actor_user_id):
        return jsonify({"error": "Only the super admin can remove ADMIN from another admin"}), 403

    updated_role_names = backend.replace_user_roles(user_id, requested_role_ids)
    if updated_role_names is None:
        return jsonify({"error": "User not found"}), 404

    updated_user = find_user_by_id(user_id)
    if not updated_user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(serialize_user_for_client(updated_user, include_roles=True))


@app.get("/api/pantries")
def list_pantries() -> Any:
    """List pantries accessible to current user."""
    pantries = pantries_for_current_user()
    for pantry in pantries:
        pantry["leads"] = get_pantry_leads(int(pantry.get("pantry_id")))
    return jsonify(pantries)


@app.get("/api/all_pantries")
def list_all_pantries() -> Any:
    """List all pantries (public endpoint, no authorization required)."""
    pantries = backend.list_pantries()
    for pantry in pantries:
        pantry["leads"] = get_pantry_leads(int(pantry.get("pantry_id")))
    return jsonify(pantries)


@app.get("/api/volunteer/pantries")
def list_volunteer_pantries() -> Any:
    user, error_response = volunteer_user_required()
    if error_response:
        return error_response

    assert user is not None
    subscriber_pantry_ids = set(backend.list_pantry_subscriptions_for_user(int(user.get("user_id"))))
    pantries = backend.list_pantries()
    payload = [volunteer_pantry_payload(pantry, subscriber_pantry_ids) for pantry in pantries]
    payload.sort(key=lambda item: str(item.get("name") or "").lower())
    return jsonify(payload)


@app.post("/api/pantries/<int:pantry_id>/subscribe")
def subscribe_to_pantry(pantry_id: int) -> Any:
    user, error_response = volunteer_user_required()
    if error_response:
        return error_response

    pantry = find_pantry_by_id(pantry_id)
    if not pantry:
        return jsonify({"error": "Pantry not found"}), 404

    assert user is not None
    user_id = int(user.get("user_id"))
    backend.subscribe_user_to_pantry(pantry_id, user_id)
    return jsonify(
        {
            "pantry_id": pantry_id,
            "is_subscribed": True,
        }
    ), 200


@app.delete("/api/pantries/<int:pantry_id>/subscribe")
def unsubscribe_from_pantry(pantry_id: int) -> Any:
    user, error_response = volunteer_user_required()
    if error_response:
        return error_response

    pantry = find_pantry_by_id(pantry_id)
    if not pantry:
        return jsonify({"error": "Pantry not found"}), 404

    assert user is not None
    user_id = int(user.get("user_id"))
    backend.unsubscribe_user_from_pantry(pantry_id, user_id)
    return jsonify(
        {
            "pantry_id": pantry_id,
            "is_subscribed": False,
        }
    ), 200




@app.get("/api/pantries/<int:pantry_id>")
def get_pantry(pantry_id: int) -> Any:
    """Get pantry by ID (public - no authorization required)."""
    pantry = find_pantry_by_id(pantry_id)
    if not pantry:
        return jsonify({"error": "Not found"}), 404

    pantry["leads"] = get_pantry_leads(pantry_id)
    return jsonify(pantry)


@app.post("/api/pantries")
def create_pantry() -> Any:
    """Create a new pantry (admin-capable actors only)."""
    user = current_user()
    if not user or not is_admin_capable(int(user.get("user_id"))):
        return jsonify({"error": "Forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    required = ["name", "location_address"]
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({"error": f"Missing: {', '.join(missing)}"}), 400

    pantry = backend.create_pantry(
        name=payload["name"],
        location_address=payload["location_address"],
        lead_ids=[int(v) for v in payload.get("lead_ids", [])],
    )
    return jsonify(pantry), 201


@app.patch("/api/pantries/<int:pantry_id>")
def update_pantry(pantry_id: int) -> Any:
    """Update pantry name or address (admin-capable actors only)."""
    user = current_user()
    if not user or not is_admin_capable(int(user.get("user_id"))):
        return jsonify({"error": "Forbidden"}), 403

    pantry = find_pantry_by_id(pantry_id)
    if not pantry:
        return jsonify({"error": "Pantry not found"}), 404

    payload = request.get_json(silent=True) or {}
    allowed_keys = {"name", "location_address"}
    payload = {k: v for k, v in payload.items() if k in allowed_keys}
    if not payload:
        return jsonify({"error": "No valid fields to update"}), 400

    updated = backend.update_pantry(pantry_id, payload)
    if not updated:
        return jsonify({"error": "Not found"}), 404

    updated["leads"] = get_pantry_leads(pantry_id)
    return jsonify(updated)


@app.delete("/api/pantries/<int:pantry_id>")
def delete_pantry(pantry_id: int) -> Any:
    """Delete a pantry (admin-capable actors only)."""
    user = current_user()
    if not user or not is_admin_capable(int(user.get("user_id"))):
        return jsonify({"error": "Forbidden"}), 403

    pantry = find_pantry_by_id(pantry_id)
    if not pantry:
        return jsonify({"error": "Pantry not found"}), 404

    backend.delete_pantry(pantry_id)
    return jsonify({"success": True}), 200


@app.post("/api/pantries/<int:pantry_id>/leads")
def add_pantry_lead(pantry_id: int) -> Any:
    """Assign a pantry lead to a pantry (admin-capable actors only)."""
    user = current_user()
    if not user or not is_admin_capable(int(user.get("user_id"))):
        return jsonify({"error": "Forbidden"}), 403

    pantry = find_pantry_by_id(pantry_id)
    if not pantry:
        return jsonify({"error": "Pantry not found"}), 404

    payload = request.get_json(silent=True) or {}
    lead_id = payload.get("user_id")
    if not lead_id:
        return jsonify({"error": "Missing user_id"}), 400

    lead = find_user_by_id(int(lead_id))
    if not lead or not user_has_role(int(lead_id), "PANTRY_LEAD"):
        return jsonify({"error": "User must have PANTRY_LEAD role"}), 400

    if backend.is_pantry_lead(pantry_id, int(lead_id)):
        return jsonify({"error": "User already a lead for this pantry"}), 400

    try:
        backend.add_pantry_lead(pantry_id, int(lead_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "pantry_id": pantry_id,
        "user_id": int(lead_id),
        "user": lead,
    }), 201


@app.delete("/api/pantries/<int:pantry_id>/leads/<int:lead_id>")
def remove_pantry_lead(pantry_id: int, lead_id: int) -> Any:
    """Remove a pantry lead from a pantry (admin-capable actors only)."""
    user = current_user()
    if not user or not is_admin_capable(int(user.get("user_id"))):
        return jsonify({"error": "Forbidden"}), 403

    pantry = find_pantry_by_id(pantry_id)
    if not pantry:
        return jsonify({"error": "Pantry not found"}), 404

    lead = find_user_by_id(lead_id)
    if not lead:
        return jsonify({"error": "User not found"}), 404

    backend.remove_pantry_lead(pantry_id, lead_id)
    return jsonify({"success": True}), 200


# ========== SHIFTS ==========

@app.get("/api/pantries/<int:pantry_id>/shifts")
def get_shifts(pantry_id: int) -> Any:
    """Get all shifts for a pantry."""
    user = current_user()
    include_cancelled = should_include_cancelled_shift_data(user, pantry_id)
    shifts = backend.list_shifts_by_pantry(pantry_id, include_cancelled=include_cancelled)

    serialized: list[dict[str, Any]] = []
    for shift in shifts:
        shift_id = int(shift.get("shift_id"))
        expire_pending_signups_if_started(shift_id)
        payload = attach_shift_recurrence_metadata(shift)
        payload["roles"] = get_shift_roles(shift_id, include_cancelled=include_cancelled)
        serialized.append(payload)
    return jsonify(serialized)

@app.get("/api/pantries/<int:pantry_id>/active-shifts")
def get_active_shifts(pantry_id: int) -> Any:
    """Get non-expired shifts for volunteer/public views."""
    shifts = backend.list_non_expired_shifts_by_pantry(pantry_id, include_cancelled=False)
    serialized: list[dict[str, Any]] = []
    for shift in shifts:
        payload = attach_shift_recurrence_metadata(shift)
        payload["roles"] = get_shift_roles(int(shift.get("shift_id")), include_cancelled=False)
        serialized.append(payload)

    return jsonify(serialized)


@app.get("/api/calendar/shifts")
def get_calendar_shifts() -> Any:
    start_param = request.args.get("start")
    end_param = request.args.get("end")
    start_time = parse_iso_datetime_to_utc(start_param)
    end_time = parse_iso_datetime_to_utc(end_param)
    if not start_time or not end_time:
        return jsonify({"error": "start and end query params are required ISO datetimes"}), 400
    if end_time < start_time:
        return jsonify({"error": "end must be greater than or equal to start"}), 400

    shifts = backend.list_non_expired_shifts_in_range(
        start_time=start_time.isoformat().replace("+00:00", "Z"),
        end_time=end_time.isoformat().replace("+00:00", "Z"),
        include_cancelled=False,
    )
    serialized: list[dict[str, Any]] = []
    for shift in shifts:
        shift_id = int(shift.get("shift_id"))
        expire_pending_signups_if_started(shift_id)
        pantry = find_pantry_by_id(int(shift.get("pantry_id")))
        shift["roles"] = get_shift_roles(shift_id, include_cancelled=False)
        shift["pantry"] = {
            "pantry_id": pantry.get("pantry_id") if pantry else shift.get("pantry_id"),
            "name": pantry.get("name") if pantry else "Unknown Pantry",
            "location_address": pantry.get("location_address") if pantry else "",
        }
        serialized.append(attach_shift_recurrence_metadata(shift))

    return jsonify(serialized)


@app.post("/api/pantries/<int:pantry_id>/shifts")
def create_shift(pantry_id: int) -> Any:
    """Create a new shift (PANTRY_LEAD or admin-capable actor)."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    user_id = int(user.get("user_id"))
    is_admin = is_admin_capable(user_id)
    is_lead = user_has_role(user_id, "PANTRY_LEAD")

    if not (is_admin or is_lead):
        return jsonify({"error": "Forbidden"}), 403

    if not is_admin and not backend.is_pantry_lead(pantry_id, user_id):
        return jsonify({"error": "Not a lead for this pantry"}), 403

    pantry = find_pantry_by_id(pantry_id)
    if not pantry:
        return jsonify({"error": "Pantry not found"}), 404

    payload = request.get_json(silent=True) or {}
    required = ["shift_name", "start_time", "end_time"]
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({"error": f"Missing: {', '.join(missing)}"}), 400

    shift = backend.create_shift(
        pantry_id=pantry_id,
        shift_name=payload["shift_name"],
        start_time=payload["start_time"],
        end_time=payload["end_time"],
        status=payload.get("status", "OPEN"),
        created_by=user_id,
    )
    shift["roles"] = []
    send_new_shift_notifications_to_subscribers_if_configured(
        pantry=pantry,
        shift=shift,
        roles=[],
    )
    return jsonify(shift), 201


@app.post("/api/pantries/<int:pantry_id>/shifts/full-create")
def create_full_shift(pantry_id: int) -> Any:
    """Create one-off or recurring shifts with roles in one request."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    user_id = int(user.get("user_id"))
    is_admin = is_admin_capable(user_id)
    is_lead = user_has_role(user_id, "PANTRY_LEAD")
    if not (is_admin or is_lead):
        return jsonify({"error": "Forbidden"}), 403
    if not is_admin and not backend.is_pantry_lead(pantry_id, user_id):
        return jsonify({"error": "Not a lead for this pantry"}), 403

    pantry = find_pantry_by_id(pantry_id)
    if not pantry:
        return jsonify({"error": "Pantry not found"}), 404

    payload = request.get_json(silent=True) or {}
    required = ["shift_name", "start_time", "end_time", "roles"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        return jsonify({"error": f"Missing: {', '.join(missing)}"}), 400

    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    start_utc = parse_iso_datetime_to_utc(start_time)
    end_utc = parse_iso_datetime_to_utc(end_time)
    if not start_utc or not end_utc or end_utc <= start_utc:
        return jsonify({"error": "Shift end time must be after start time"}), 400

    try:
        roles_payload = normalize_shift_roles_payload(payload.get("roles"))
        recurrence = normalize_recurrence_payload(payload.get("recurrence"), start_time=start_time)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not recurrence:
        created_shift = create_shift_with_roles(
            pantry_id=pantry_id,
            created_by=user_id,
            shift_name=str(payload.get("shift_name")),
            start_time=start_time,
            end_time=end_time,
            status=str(payload.get("status", "OPEN")).upper(),
            roles_payload=roles_payload,
        )
        send_new_shift_notifications_to_subscribers_if_configured(
            pantry=pantry,
            shift=created_shift,
            roles=created_shift.get("roles", []),
        )
        response = {
            "created_shift_count": 1,
            "first_shift": created_shift,
            "shift_series_id": None,
        }
        return jsonify(response), 201

    series = backend.create_shift_series(
        recurrence_payload_for_series_create(
            pantry_id=pantry_id,
            created_by=user_id,
            recurrence=recurrence,
        )
    )
    occurrences = generate_weekly_occurrences(start_time, end_time, recurrence)
    created_shifts: list[dict[str, Any]] = []
    for index, occurrence in enumerate(occurrences, start=1):
        created_shifts.append(
            create_shift_with_roles(
                pantry_id=pantry_id,
                created_by=user_id,
                shift_name=str(payload.get("shift_name")),
                start_time=occurrence["start_time"],
                end_time=occurrence["end_time"],
                status=str(payload.get("status", "OPEN")).upper(),
                roles_payload=roles_payload,
                shift_series_id=int(series.get("shift_series_id")),
                series_position=index,
            )
        )

    if created_shifts:
        send_new_shift_notifications_to_subscribers_if_configured(
            pantry=pantry,
            shift=created_shifts[0],
            roles=created_shifts[0].get("roles", []),
            recurrence=recurrence_for_client(series),
            created_shift_count=len(created_shifts),
            preview_occurrences=created_shifts[:3],
        )

    return jsonify(
        {
            "created_shift_count": len(created_shifts),
            "first_shift": created_shifts[0] if created_shifts else None,
            "shift_series_id": int(series.get("shift_series_id")),
        }
    ), 201


@app.get("/api/shifts/<int:shift_id>")
def get_shift(shift_id: int) -> Any:
    """Get a single shift with its roles."""
    shift = backend.get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Not found"}), 404

    expire_pending_signups_if_started(shift_id)

    user = current_user()
    pantry_id = int(shift.get("pantry_id"))
    include_cancelled = should_include_cancelled_shift_data(user, pantry_id)
    payload = attach_shift_recurrence_metadata(shift, include_recurrence=True)
    payload["roles"] = get_shift_roles(shift_id, include_cancelled=include_cancelled)
    return jsonify(payload)


@app.get("/api/shifts/<int:shift_id>/registrations")
def get_shift_registrations(shift_id: int) -> Any:
    """Get shift roles with registered volunteers (PANTRY_LEAD or admin-capable actor)."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    shift = backend.get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Not found"}), 404

    user_id = int(user.get("user_id"))
    is_admin = is_admin_capable(user_id)
    pantry_id = int(shift.get("pantry_id"))

    if not is_admin and not backend.is_pantry_lead(pantry_id, user_id):
        return jsonify({"error": "Forbidden"}), 403

    expire_pending_signups_if_started(shift_id)

    roles_with_signups: list[dict[str, Any]] = []
    for role in get_shift_roles(shift_id, include_cancelled=True):
        role_id = int(role.get("shift_role_id"))
        signups = get_shift_signups(role_id)
        pending_reconfirm_count = 0

        enriched_signups: list[dict[str, Any]] = []
        for signup in signups:
            signup_status = str(signup.get("signup_status", "")).upper()
            if signup_status == SIGNUP_STATUS_PENDING_CONFIRMATION:
                pending_reconfirm_count += 1
                continue
            if signup_status not in LEAD_VISIBLE_SIGNUP_STATUSES:
                continue
            signup_with_user = dict(signup)
            signup_user = find_user_by_id(int(signup.get("user_id")))
            signup_with_user["user"] = serialize_signup_user(signup_user)
            enriched_signups.append(signup_with_user)

        role_with_signups = dict(role)
        role_with_signups["signups"] = enriched_signups
        role_with_signups["pending_reconfirm_count"] = pending_reconfirm_count
        roles_with_signups.append(role_with_signups)

    response = {
        "shift_id": shift.get("shift_id"),
        "shift_name": shift.get("shift_name"),
        "pantry_id": shift.get("pantry_id"),
        "start_time": shift.get("start_time"),
        "end_time": shift.get("end_time"),
        "roles": roles_with_signups,
    }
    return jsonify(response)


@app.patch("/api/shifts/<int:shift_id>")
def update_shift(shift_id: int) -> Any:
    """Update shift (PANTRY_LEAD or admin-capable actor)."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    shift = backend.get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Not found"}), 404

    user_id = int(user.get("user_id"))
    if not ensure_shift_manager_permission(user_id, shift):
        return jsonify({"error": "Forbidden"}), 403
    if shift_has_ended(shift):
        return past_shift_locked_response()

    payload = request.get_json(silent=True) or {}
    allowed_keys = {"shift_name", "start_time", "end_time", "status"}
    payload = {key: value for key, value in payload.items() if key in allowed_keys}
    if not payload:
        return jsonify({"error": "No valid fields to update"}), 400

    previous_status = str(shift.get("status", "OPEN")).upper()
    updated = backend.update_shift(shift_id, payload)
    if not updated:
        return jsonify({"error": "Not found"}), 404

    affected = mark_shift_signups_pending(shift_id)
    notification_signups = affected.pop("affected_signups", [])
    recalculate_shift_capacities(shift_id)
    updated["roles"] = get_shift_roles(shift_id, include_cancelled=True)
    updated.update(affected)
    if affected["affected_signup_count"] > 0:
        next_status = str(updated.get("status", "OPEN")).upper()
        notification_type = "cancel" if next_status == "CANCELLED" else "update"
        if notification_type == "cancel" and previous_status == "CANCELLED":
            return jsonify(updated)
        send_shift_notifications_if_configured(
            notification_type=notification_type,
            shift=updated,
            signups=notification_signups,
        )
    return jsonify(updated)


@app.put("/api/shifts/<int:shift_id>/full-update")
def replace_shift_and_roles(shift_id: int) -> Any:
    """Update a shift and its roles in one request to avoid duplicate notifications."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    shift = backend.get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Not found"}), 404

    user_id = int(user.get("user_id"))
    if not ensure_shift_manager_permission(user_id, shift):
        return jsonify({"error": "Forbidden"}), 403
    if shift_has_ended(shift):
        return past_shift_locked_response()

    payload = request.get_json(silent=True) or {}
    try:
        normalized_roles = normalize_shift_roles_payload(payload.get("roles"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    apply_scope = str(payload.get("apply_scope") or "single").strip().lower()
    if apply_scope not in {"single", "future"}:
        return jsonify({"error": "apply_scope must be single or future"}), 400
    if apply_scope == "future" and not shift.get("shift_series_id"):
        return jsonify({"error": "apply_scope future is only available for recurring shifts"}), 400

    shift_payload = {
        key: value
        for key, value in payload.items()
        if key in {"shift_name", "start_time", "end_time", "status"}
    }

    try:
        recurrence = normalize_recurrence_payload(payload.get("recurrence"), start_time=shift_payload.get("start_time", shift.get("start_time")))
        if apply_scope == "future":
            future_roles_payload = [
                {
                    "role_title": role["role_title"],
                    "required_count": role["required_count"],
                }
                for role in normalized_roles
            ]
            updated = split_series_update_targets(
                current_shift=shift,
                shift_payload=shift_payload,
                roles_payload=future_roles_payload,
                recurrence=recurrence,
                actor_user_id=user_id,
            )
        else:
            updated = apply_single_shift_update_with_roles(
                shift_id=shift_id,
                shift_payload=shift_payload,
                roles_payload=normalized_roles,
            )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not updated:
        return jsonify({"error": "Not found"}), 404
    return jsonify(updated)


@app.delete("/api/shifts/<int:shift_id>")
def delete_shift(shift_id: int) -> Any:
    """Cancel a shift (PANTRY_LEAD or admin-capable actor)."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    shift = backend.get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Not found"}), 404

    user_id = int(user.get("user_id"))
    if not ensure_shift_manager_permission(user_id, shift):
        return jsonify({"error": "Forbidden"}), 403
    if shift_has_ended(shift):
        return past_shift_locked_response()

    updated_shift = cancel_single_shift_for_manager(shift_id)
    if not updated_shift:
        return jsonify({"error": "Not found"}), 404
    return jsonify(updated_shift), 200


@app.post("/api/shifts/<int:shift_id>/cancel")
def cancel_shift_scoped(shift_id: int) -> Any:
    """Cancel a shift or recurring series slice."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    shift = backend.get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Not found"}), 404

    user_id = int(user.get("user_id"))
    if not ensure_shift_manager_permission(user_id, shift):
        return jsonify({"error": "Forbidden"}), 403
    if shift_has_ended(shift):
        return past_shift_locked_response()

    payload = request.get_json(silent=True) or {}
    apply_scope = str(payload.get("apply_scope") or "single").strip().lower()
    if apply_scope not in {"single", "future"}:
        return jsonify({"error": "apply_scope must be single or future"}), 400
    if apply_scope == "future" and not shift.get("shift_series_id"):
        return jsonify({"error": "apply_scope future is only available for recurring shifts"}), 400

    response = cancel_future_series_from(shift) if apply_scope == "future" else cancel_single_shift_for_manager(shift_id)
    if not response:
        return jsonify({"error": "Not found"}), 404
    return jsonify(response), 200


# ========== SHIFT ROLES ==========

@app.post("/api/shifts/<int:shift_id>/roles")
def create_shift_role(shift_id: int) -> Any:
    """Create a role/position within a shift."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    shift = backend.get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Shift not found"}), 404

    user_id = int(user.get("user_id"))
    is_admin = is_admin_capable(user_id)
    pantry_id = int(shift.get("pantry_id"))

    if not is_admin and not backend.is_pantry_lead(pantry_id, user_id):
        return jsonify({"error": "Forbidden"}), 403
    if shift_has_ended(shift):
        return past_shift_locked_response()
    if str(shift.get("status", "OPEN")).upper() == "CANCELLED":
        return jsonify({"error": "Cannot add roles to a cancelled shift"}), 400

    payload = request.get_json(silent=True) or {}
    required = ["role_title", "required_count"]
    missing = [k for k in required if k not in payload]
    if missing:
        return jsonify({"error": f"Missing: {', '.join(missing)}"}), 400

    try:
        required_count = int(payload["required_count"])
        if required_count < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "required_count must be >= 1"}), 400

    role = backend.create_shift_role(
        shift_id=shift_id,
        role_title=payload["role_title"],
        required_count=required_count,
    )
    return jsonify(role), 201


@app.patch("/api/shift-roles/<int:shift_role_id>")
def update_shift_role(shift_role_id: int) -> Any:
    """Update a shift role (PANTRY_LEAD or admin-capable actor)."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    shift_role = backend.get_shift_role_by_id(shift_role_id)
    if not shift_role:
        return jsonify({"error": "Not found"}), 404

    shift = backend.get_shift_by_id(int(shift_role.get("shift_id")))
    if not shift:
        return jsonify({"error": "Shift not found"}), 404

    user_id = int(user.get("user_id"))
    if not ensure_shift_manager_permission(user_id, shift):
        return jsonify({"error": "Forbidden"}), 403
    if shift_has_ended(shift):
        return past_shift_locked_response()

    payload = request.get_json(silent=True) or {}
    allowed_keys = {"role_title", "required_count", "status"}
    payload = {key: value for key, value in payload.items() if key in allowed_keys}
    if not payload:
        return jsonify({"error": "No valid fields to update"}), 400

    if "required_count" in payload:
        try:
            required_count = int(payload["required_count"])
            if required_count < 1:
                raise ValueError
            payload["required_count"] = required_count
        except (TypeError, ValueError):
            return jsonify({"error": "required_count must be >= 1"}), 400

    updated = backend.update_shift_role(shift_role_id, payload)
    if not updated:
        return jsonify({"error": "Not found"}), 404

    shift_id = int(shift.get("shift_id"))
    affected = mark_shift_signups_pending(shift_id)
    notification_signups = affected.pop("affected_signups", [])
    recalculate_shift_role_capacity(shift_role_id)
    updated = backend.get_shift_role_by_id(shift_role_id) or updated
    updated.update(affected)
    if affected["affected_signup_count"] > 0:
        shift_with_roles = backend.get_shift_by_id(shift_id) or shift
        shift_with_roles["roles"] = get_shift_roles(shift_id, include_cancelled=True)
        send_shift_notifications_if_configured(
            notification_type="update",
            shift=shift_with_roles,
            signups=notification_signups,
        )
    return jsonify(updated)


@app.delete("/api/shift-roles/<int:shift_role_id>")
def delete_shift_role(shift_role_id: int) -> Any:
    """Delete or disable a shift role with reconfirmation behavior."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    shift_role = backend.get_shift_role_by_id(shift_role_id)
    if not shift_role:
        return jsonify({"error": "Not found"}), 404

    shift = backend.get_shift_by_id(int(shift_role.get("shift_id")))
    if not shift:
        return jsonify({"error": "Shift not found"}), 404

    user_id = int(user.get("user_id"))
    if not ensure_shift_manager_permission(user_id, shift):
        return jsonify({"error": "Forbidden"}), 403
    if shift_has_ended(shift):
        return past_shift_locked_response()

    signups = backend.list_shift_signups(shift_role_id)
    if not signups:
        backend.delete_shift_role(shift_role_id)
        return jsonify({"success": True, "affected_signup_count": 0, "affected_volunteer_contacts": []}), 200

    updated_role = backend.update_shift_role(shift_role_id, {"status": "CANCELLED", "filled_count": 0})
    affected = mark_shift_signups_pending(int(shift.get("shift_id")))
    notification_signups = affected.pop("affected_signups", [])
    recalculate_shift_role_capacity(shift_role_id)
    updated_role = backend.get_shift_role_by_id(shift_role_id) or updated_role

    response = {
        "success": True,
        "role": updated_role,
        **affected,
    }
    if affected["affected_signup_count"] > 0:
        shift_with_roles = backend.get_shift_by_id(int(shift.get("shift_id"))) or shift
        shift_with_roles["roles"] = get_shift_roles(int(shift.get("shift_id")), include_cancelled=True)
        send_shift_notifications_if_configured(
            notification_type="update",
            shift=shift_with_roles,
            signups=notification_signups,
        )
    return jsonify(response), 200


# ========== SHIFT SIGNUPS ==========

@app.post("/api/shift-roles/<int:shift_role_id>/signup")
def create_signup(shift_role_id: int) -> Any:
    """Volunteer signs up for a shift role."""
    user = current_user()
    if not user or not user_has_role(int(user.get("user_id")), "VOLUNTEER"):
        return jsonify({"error": "Forbidden or not a volunteer"}), 403

    shift_role = backend.get_shift_role_by_id(shift_role_id)
    if not shift_role:
        return jsonify({"error": "Shift role not found"}), 404

    shift = backend.get_shift_by_id(int(shift_role.get("shift_id")))
    if not shift:
        return jsonify({"error": "Shift not found"}), 404

    payload = request.get_json(silent=True) or {}
    payload_user_id = payload.get("user_id")

    # Users can only sign themselves up.
    current_user_id = int(user.get("user_id"))
    if payload_user_id and int(payload_user_id) != current_user_id:
        return jsonify({"error": "Users can only sign themselves up"}), 403
    user_id = int(payload_user_id or current_user_id)

    expire_pending_signups_if_started(int(shift.get("shift_id")))

    if str(shift.get("status", "OPEN")).upper() == "CANCELLED":
        return jsonify({"error": "Shift is cancelled"}), 400
    if shift_has_ended(shift):
        return jsonify({"error": "Shift has ended"}), 400
    if str(shift_role.get("status", "OPEN")).upper() == "CANCELLED":
        return jsonify({"error": "Shift role is cancelled"}), 400

    now_utc = datetime.now(timezone.utc)
    signups_by_user = backend.list_signups_by_user(user_id)

    cooldown_ends_at = signup_rate_limit_cooldown_ends_at(signups_by_user, now_utc)
    if cooldown_ends_at is not None:
        return (
            jsonify(
                {
                    "error": f"You can sign up for at most {MAX_SIGNUPS_PER_24_HOURS} shifts within 24 hours",
                    "code": "SIGNUP_RATE_LIMITED",
                    "cooldown_ends_at": cooldown_ends_at.isoformat().replace("+00:00", "Z"),
                }
            ),
            429,
        )

    has_conflict = any(
        signup_row_blocks_overlap(signup_row, now_utc)
        and signup_row_overlaps_shift(signup_row, shift, shift_role_id)
        for signup_row in signups_by_user
    )
    if has_conflict:
        return jsonify({"error": "Can't register for overlapping shift"}), 400

    try:
        signup = backend.create_signup(
            shift_role_id=shift_role_id,
            user_id=user_id,
            signup_status=payload.get("signup_status", "CONFIRMED"),
        )
    except LookupError:
        return jsonify({"error": "Shift role not found"}), 404
    except ValueError as exc:
        if str(exc) == "Already signed up":
            return jsonify({"error": "Already signed up", "code": "ALREADY_SIGNED_UP"}), 409
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    recalculate_shift_role_capacity(shift_role_id)
    signup_user = find_user_by_id(user_id)
    signup["user"] = serialize_signup_user(signup_user)
    send_signup_confirmation_if_configured(signup, signup_user, shift, shift_role)
    return jsonify(signup), 201


@app.get("/api/shift-roles/<int:shift_role_id>/signups")
def get_signups_for_role(shift_role_id: int) -> Any:
    """Get all signups for a shift role."""
    shift_role = backend.get_shift_role_by_id(shift_role_id)
    if not shift_role:
        return jsonify({"error": "Not found"}), 404

    expire_pending_signups_if_started(int(shift_role.get("shift_id")))
    signups = get_shift_signups(shift_role_id)
    for signup in signups:
        signup["user"] = serialize_signup_user(find_user_by_id(int(signup.get("user_id"))))

    return jsonify(signups)


@app.delete("/api/signups/<int:signup_id>")
def delete_signup(signup_id: int) -> Any:
    """Cancel a signup."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    signup = backend.get_signup_by_id(signup_id)
    if not signup:
        return jsonify({"error": "Not found"}), 404

    user_id = int(user.get("user_id"))
    signup_user_id = int(signup.get("user_id"))
    is_admin = is_admin_capable(user_id)

    if user_id != signup_user_id and not is_admin:
        return jsonify({"error": "Forbidden"}), 403

    backend.delete_signup(signup_id)
    return jsonify({"success": True}), 200


@app.patch("/api/signups/<int:signup_id>/reconfirm")
def reconfirm_signup(signup_id: int) -> Any:
    """Volunteer reconfirm/cancel after shift edits."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    signup = backend.get_signup_by_id(signup_id)
    if not signup:
        return jsonify({"error": "Not found"}), 404

    current_user_id = int(user.get("user_id"))
    signup_user_id = int(signup.get("user_id"))
    is_admin = is_admin_capable(current_user_id)
    if current_user_id != signup_user_id and not is_admin:
        return jsonify({"error": "Forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action", "")).strip().upper()
    if action not in {"CONFIRM", "CANCEL"}:
        return jsonify({"error": "action must be CONFIRM or CANCEL"}), 400

    signup, shift_role, shift = get_signup_shift_context(signup_id)
    if not signup:
        return jsonify({"error": "Not found"}), 404
    if not shift_role or not shift:
        return jsonify({"error": "Shift context not found"}), 404

    shift_id = int(shift.get("shift_id"))
    expire_pending_signups_if_started(shift_id)
    signup = backend.get_signup_by_id(signup_id)
    if not signup:
        return jsonify({"error": "Not found"}), 404

    current_status = str(signup.get("signup_status", "")).upper()
    if action == "CANCEL":
        backend.delete_signup(signup_id)
        return jsonify({"success": True, "removed_signup_id": signup_id}), 200

    if current_status != SIGNUP_STATUS_PENDING_CONFIRMATION:
        return jsonify({"error": "Signup is not pending confirmation"}), 400

    reconfirm_result = backend.reconfirm_pending_signup(signup_id, utc_now_iso())
    result_code = str(reconfirm_result.get("result", "")).upper()
    updated_signup = reconfirm_result.get("signup")
    recalculate_shift_role_capacity(int(shift_role.get("shift_role_id")))

    if result_code == "NOT_FOUND" or not updated_signup:
        return jsonify({"error": "Not found"}), 404
    if result_code == "CONFIRMED":
        return jsonify(updated_signup), 200
    if result_code == "WAITLISTED":
        return (
            jsonify({"error": "ROLE_FULL_OR_UNAVAILABLE", "code": "ROLE_FULL_OR_UNAVAILABLE", "signup": updated_signup}),
            409,
        )
    if result_code == "EXPIRED":
        return (
            jsonify({"error": "RESERVATION_EXPIRED", "code": "RESERVATION_EXPIRED", "signup": updated_signup}),
            409,
        )
    if result_code == "NOT_PENDING":
        return jsonify({"error": "Signup is not pending confirmation"}), 400

    return jsonify({"error": "Unable to reconfirm signup"}), 400


@app.patch("/api/signups/<int:signup_id>/attendance")
def mark_signup_attendance(signup_id: int) -> Any:
    """Mark signup attendance as SHOW_UP or NO_SHOW (PANTRY_LEAD for pantry or admin-capable actor)."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    if "attendance_status" not in payload:
        return jsonify({"error": "Missing attendance_status"}), 400

    updated, error = set_attendance_status(
        signup_id=signup_id,
        attendance_status=payload.get("attendance_status"),
        actor_user_id=int(user.get("user_id")),
    )
    if error:
        message, status_code = error
        return jsonify({"error": message}), status_code

    return jsonify(updated), 200


@app.patch("/api/signups/<int:signup_id>")
def update_signup(signup_id: int) -> Any:
    """Update signup status (admin-capable actors only)."""
    user = current_user()
    if not user or not is_admin_capable(int(user.get("user_id"))):
        return jsonify({"error": "Forbidden"}), 403

    signup = backend.get_signup_by_id(signup_id)
    if not signup:
        return jsonify({"error": "Not found"}), 404

    payload = request.get_json(silent=True) or {}
    if "signup_status" in payload:
        requested_status = str(payload["signup_status"]).strip().upper()
        if requested_status in ATTENDANCE_STATUSES:
            updated, error = set_attendance_status(
                signup_id=signup_id,
                attendance_status=requested_status,
                actor_user_id=int(user.get("user_id")),
            )
            if error:
                message, status_code = error
                return jsonify({"error": message}), status_code
            signup = updated
        else:
            updated = backend.update_signup(signup_id, requested_status)
            if updated:
                signup = updated

    return jsonify(signup)


# ========== PUBLIC ==========

@app.get("/api/public/pantries")
def get_public_pantries() -> Any:
    """List all pantries (public endpoint)."""
    return jsonify(backend.list_pantries())


@app.get("/api/public/pantries/<slug>/shifts")
def get_public_shifts(slug: str) -> Any:
    """Public endpoint: get shifts for a pantry (no auth)."""
    pantry = backend.get_pantry_by_slug(slug)
    if not pantry:
        return jsonify([])

    pantry_id = int(pantry.get("pantry_id"))
    shifts = backend.list_shifts_by_pantry(pantry_id, include_cancelled=False)

    for shift in shifts:
        shift_id = int(shift.get("shift_id"))
        expire_pending_signups_if_started(shift_id)
        shift["roles"] = get_shift_roles(shift_id, include_cancelled=False)

    return jsonify(shifts)


# ========== PAGES ==========

@app.get("/")
def index() -> Any:
    """Main dashboard - unified page for all roles."""
    return render_template("dashboard.html")


@app.get("/healthz")
def healthcheck() -> tuple[dict[str, str], int]:
    return {"status": "ok"}, 200


@app.get("/dashboard")
def dashboard() -> Any:
    """Main dashboard - unified page for all roles."""
    return render_template("dashboard.html")


if __name__ == "__main__":
    app.run(debug=not IS_PRODUCTION, port=int(os.getenv("PORT", "5000")), host="0.0.0.0")
