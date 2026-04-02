from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
from typing import Any

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request, session
from flask_cors import CORS

from auth import AuthError, create_auth_service
from backends.base import StoreBackend
from backends.factory import create_backend
from notifications import (
    send_shift_cancellation_notification,
    send_shift_update_notification,
    send_signup_confirmation,
)

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")

app = Flask(
    __name__,
    static_folder=str(ROOT_DIR / "frontend" / "static"),
    template_folder=str(ROOT_DIR / "frontend" / "templates"),
)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "volunteer-managing-dev-secret")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
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
ADMIN_ROLE_NAME = "ADMIN"
SUPER_ADMIN_ROLE_NAME = "SUPER_ADMIN"
PROTECTED_SUPER_ADMIN_USER_ID = 1
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
    return find_user_by_id(user_id)


def serialize_user_for_client(user: dict[str, Any] | None, include_roles: bool = False) -> dict[str, Any] | None:
    if not user:
        return None

    linked_auth_provider = user.get("auth_provider") or ("memory" if auth_service.mode == "memory" else None)
    payload = {
        "user_id": user.get("user_id"),
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "phone_number": user.get("phone_number"),
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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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

    for shift in shifts:
        shift_id = int(shift.get("shift_id"))
        expire_pending_signups_if_started(shift_id)
        shift["roles"] = get_shift_roles(shift_id, include_cancelled=include_cancelled)
    return jsonify(shifts)

@app.get("/api/pantries/<int:pantry_id>/active-shifts")
def get_active_shifts(pantry_id: int) -> Any:
    """Get non-expired shifts for volunteer/public views."""
    shifts = backend.list_non_expired_shifts_by_pantry(pantry_id, include_cancelled=False)
    for shift in shifts:
        shift["roles"] = get_shift_roles(int(shift.get("shift_id")), include_cancelled=False)

    return jsonify(shifts)


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
    return jsonify(shift), 201


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
    shift["roles"] = get_shift_roles(shift_id, include_cancelled=include_cancelled)
    return jsonify(shift)


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
    roles_payload = payload.get("roles")
    if not isinstance(roles_payload, list):
        return jsonify({"error": "roles must be an array"}), 400

    shift_payload = {
        key: value
        for key, value in payload.items()
        if key in {"shift_name", "start_time", "end_time", "status"}
    }

    normalized_roles: list[dict[str, Any]] = []
    seen_role_ids: set[int] = set()
    for role_payload in roles_payload:
        if not isinstance(role_payload, dict):
            return jsonify({"error": "Each role must be an object"}), 400

        role_title = str(role_payload.get("role_title") or "").strip()
        if not role_title:
            return jsonify({"error": "role_title is required"}), 400

        try:
            required_count = int(role_payload.get("required_count"))
        except (TypeError, ValueError):
            return jsonify({"error": "required_count must be >= 1"}), 400
        if required_count < 1:
            return jsonify({"error": "required_count must be >= 1"}), 400

        normalized_role: dict[str, Any] = {
            "role_title": role_title,
            "required_count": required_count,
        }
        raw_role_id = role_payload.get("shift_role_id")
        if raw_role_id is not None:
            role_id = int(raw_role_id)
            if role_id in seen_role_ids:
                return jsonify({"error": "Duplicate shift_role_id in roles payload"}), 400
            seen_role_ids.add(role_id)
            normalized_role["shift_role_id"] = role_id
        normalized_roles.append(normalized_role)

    try:
        updated = backend.replace_shift_and_roles(
            shift_id=shift_id,
            shift_payload=shift_payload,
            roles_payload=normalized_roles,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not updated:
        return jsonify({"error": "Not found"}), 404

    affected = mark_shift_signups_pending(shift_id)
    notification_signups = affected.pop("affected_signups", [])
    recalculate_shift_capacities(shift_id)
    updated["roles"] = get_shift_roles(shift_id, include_cancelled=True)
    updated.update(affected)
    if affected["affected_signup_count"] > 0:
        send_shift_notifications_if_configured(
            notification_type="update",
            shift=updated,
            signups=notification_signups,
        )
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

    previous_status = str(shift.get("status", "OPEN")).upper()
    updated_shift = backend.update_shift(shift_id, {"status": "CANCELLED"})
    if not updated_shift:
        return jsonify({"error": "Not found"}), 404

    affected = mark_shift_signups_pending(shift_id)
    notification_signups = affected.pop("affected_signups", [])
    recalculate_shift_capacities(shift_id)
    updated_shift["roles"] = get_shift_roles(shift_id, include_cancelled=True)
    updated_shift.update(affected)
    if previous_status != "CANCELLED" and affected["affected_signup_count"] > 0:
        send_shift_notifications_if_configured(
            notification_type="cancel",
            shift=updated_shift,
            signups=notification_signups,
        )
    return jsonify(updated_shift), 200


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
            existing = next(
                (s for s in get_shift_signups(shift_role_id) if int(s.get("user_id")) == user_id),
                None,
            )
            if existing:
                existing["user"] = serialize_signup_user(find_user_by_id(user_id))
                existing["already_signed_up"] = True
                return jsonify(existing), 200
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    recalculate_shift_role_capacity(shift_role_id)
    signup["already_signed_up"] = False
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


@app.get("/dashboard")
def dashboard() -> Any:
    """Main dashboard - unified page for all roles."""
    return render_template("dashboard.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000, host='0.0.0.0')
