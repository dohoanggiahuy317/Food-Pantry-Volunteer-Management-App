from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request
from flask_cors import CORS

from backends.base import StoreBackend
from backends.factory import create_backend

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")

app = Flask(
    __name__,
    static_folder=str(ROOT_DIR / "frontend" / "static"),
    template_folder=str(ROOT_DIR / "frontend" / "templates"),
)
CORS(app, resources={r"/*": {"origins": "*"}})

backend: StoreBackend = create_backend()

# Mock current user (no auth yet): default to user id=4 (admin)
DEFAULT_USER_ID = 4
ATTENDANCE_STATUSES = {"SHOW_UP", "NO_SHOW"}
SIGNUP_STATUS_PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
SIGNUP_STATUS_CONFIRMED = "CONFIRMED"
SIGNUP_STATUS_WAITLISTED = "WAITLISTED"
SIGNUP_STATUS_CANCELLED = "CANCELLED"
PAST_SHIFT_LOCK_CODE = "PAST_SHIFT_LOCKED"
ACTIVE_SIGNUP_STATUSES = {SIGNUP_STATUS_CONFIRMED, "SHOW_UP", "NO_SHOW"}
LEAD_VISIBLE_SIGNUP_STATUSES = ACTIVE_SIGNUP_STATUSES
RESERVATION_WINDOW_HOURS = 48


@app.before_request
def set_current_user() -> None:
    """Allow switching user via ?user_id=X query parameter for testing."""
    user_id = request.args.get("user_id", type=int) or DEFAULT_USER_ID
    g.current_user_id = user_id


def find_user_by_id(user_id: int) -> dict[str, Any] | None:
    return backend.get_user_by_id(user_id)


def get_user_roles(user_id: int) -> list[str]:
    return backend.get_user_roles(user_id)


def user_has_role(user_id: int, role_name: str) -> bool:
    return role_name in get_user_roles(user_id)


def current_user() -> dict[str, Any] | None:
    user_id = getattr(g, "current_user_id", DEFAULT_USER_ID)
    return find_user_by_id(user_id)


def find_pantry_by_id(pantry_id: int) -> dict[str, Any] | None:
    return backend.get_pantry_by_id(pantry_id)


def pantries_for_current_user() -> list[dict[str, Any]]:
    """Pantries the current user leads (or all if ADMIN)."""
    user = current_user()
    if not user:
        return []

    user_id = int(user.get("user_id"))
    all_pantries = backend.list_pantries()

    if user_has_role(user_id, "ADMIN"):
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
    if user_has_role(user_id, "ADMIN"):
        return True
    pantry_id = int(shift.get("pantry_id"))
    return backend.is_pantry_lead(pantry_id, user_id)


def should_include_cancelled_shift_data(user: dict[str, Any] | None, pantry_id: int) -> bool:
    if not user:
        return False
    user_id = int(user.get("user_id"))
    if user_has_role(user_id, "ADMIN"):
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


def mark_shift_signups_pending(shift_id: int) -> dict[str, Any]:
    shift = backend.get_shift_by_id(shift_id)
    if not shift or not is_upcoming_shift(shift):
        return {"affected_signup_count": 0, "affected_volunteer_contacts": []}

    reservation_expires_at = (datetime.now(timezone.utc) + timedelta(hours=RESERVATION_WINDOW_HOURS)).isoformat().replace("+00:00", "Z")
    changed_signups = backend.bulk_mark_shift_signups_pending(shift_id, reservation_expires_at)

    recalculate_shift_capacities(shift_id)
    contacts = affected_contacts_from_signups(changed_signups)
    return {
        "affected_signup_count": len(changed_signups),
        "affected_volunteer_contacts": contacts,
    }


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
    is_admin = user_has_role(actor_user_id, "ADMIN")
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

@app.get("/api/me")
def get_current_user() -> Any:
    """Get current logged-in user with roles."""
    user = current_user()
    if not user:
        return jsonify({"error": "No user"}), 401
    roles = get_user_roles(int(user.get("user_id")))
    resp = dict(user)
    resp["roles"] = roles
    return jsonify(resp)


@app.get("/api/users")
def list_users() -> Any:
    """List all users (ADMIN only). Optional role filter: ?role=PANTRY_LEAD."""
    user = current_user()
    if not user or not user_has_role(int(user.get("user_id")), "ADMIN"):
        return jsonify({"error": "Forbidden"}), 403

    role_filter = request.args.get("role")
    users = backend.list_users(role_filter)

    for u in users:
        u["roles"] = get_user_roles(int(u.get("user_id")))

    return jsonify(users)


@app.get("/api/users/<int:user_id>/signups")
def list_user_signups(user_id: int) -> Any:
    """List signups for a specific user (self or ADMIN)."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    current_user_id = int(user.get("user_id"))
    is_admin = user_has_role(current_user_id, "ADMIN")
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
    """Create a new user (ADMIN only)."""
    user = current_user()
    if not user or not user_has_role(int(user.get("user_id")), "ADMIN"):
        return jsonify({"error": "Forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    required = ["full_name", "email", "password_hash"]
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({"error": f"Missing: {', '.join(missing)}"}), 400

    try:
        new_user = backend.create_user(
            full_name=payload["full_name"],
            email=payload["email"],
            password_hash=payload["password_hash"],
            is_active=payload.get("is_active", True),
            roles=list(payload.get("roles", [])),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(new_user), 201


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
    """Create a new pantry (ADMIN only)."""
    user = current_user()
    if not user or not user_has_role(int(user.get("user_id")), "ADMIN"):
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


@app.post("/api/pantries/<int:pantry_id>/leads")
def add_pantry_lead(pantry_id: int) -> Any:
    """Assign a pantry lead to a pantry (ADMIN only)."""
    user = current_user()
    if not user or not user_has_role(int(user.get("user_id")), "ADMIN"):
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
    """Remove a pantry lead from a pantry (ADMIN only)."""
    user = current_user()
    if not user or not user_has_role(int(user.get("user_id")), "ADMIN"):
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
    """Create a new shift (PANTRY_LEAD or ADMIN)."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    user_id = int(user.get("user_id"))
    is_admin = user_has_role(user_id, "ADMIN")
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
    """Get shift roles with registered volunteers (PANTRY_LEAD or ADMIN)."""
    user = current_user()
    if not user:
        return jsonify({"error": "Forbidden"}), 403

    shift = backend.get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Not found"}), 404

    user_id = int(user.get("user_id"))
    is_admin = user_has_role(user_id, "ADMIN")
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
    """Update shift (PANTRY_LEAD or ADMIN)."""
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

    updated = backend.update_shift(shift_id, payload)
    if not updated:
        return jsonify({"error": "Not found"}), 404

    affected = mark_shift_signups_pending(shift_id)
    recalculate_shift_capacities(shift_id)
    updated["roles"] = get_shift_roles(shift_id, include_cancelled=True)
    updated.update(affected)
    return jsonify(updated)


@app.delete("/api/shifts/<int:shift_id>")
def delete_shift(shift_id: int) -> Any:
    """Cancel a shift (PANTRY_LEAD or ADMIN)."""
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

    updated_shift = backend.update_shift(shift_id, {"status": "CANCELLED"})
    if not updated_shift:
        return jsonify({"error": "Not found"}), 404

    affected = mark_shift_signups_pending(shift_id)
    recalculate_shift_capacities(shift_id)
    updated_shift["roles"] = get_shift_roles(shift_id, include_cancelled=True)
    updated_shift.update(affected)
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
    is_admin = user_has_role(user_id, "ADMIN")
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
    """Update a shift role (PANTRY_LEAD or ADMIN)."""
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
    recalculate_shift_role_capacity(shift_role_id)
    updated = backend.get_shift_role_by_id(shift_role_id) or updated
    updated.update(affected)
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
    recalculate_shift_role_capacity(shift_role_id)
    updated_role = backend.get_shift_role_by_id(shift_role_id) or updated_role

    response = {
        "success": True,
        "role": updated_role,
        **affected,
    }
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

    expire_pending_signups_if_started(int(shift.get("shift_id")))

    if str(shift.get("status", "OPEN")).upper() == "CANCELLED":
        return jsonify({"error": "Shift is cancelled"}), 400
    if shift_has_ended(shift):
        return jsonify({"error": "Shift has ended"}), 400
    if str(shift_role.get("status", "OPEN")).upper() == "CANCELLED":
        return jsonify({"error": "Shift role is cancelled"}), 400

    payload = request.get_json(silent=True) or {}
    payload_user_id = payload.get("user_id")

    # Users can only sign themselves up.
    current_user_id = int(user.get("user_id"))
    if payload_user_id and int(payload_user_id) != current_user_id:
        return jsonify({"error": "Users can only sign themselves up"}), 403
    user_id = int(payload_user_id or current_user_id)

    try:
        signup = backend.create_signup(
            shift_role_id=shift_role_id,
            user_id=user_id,
            signup_status=payload.get("signup_status", "CONFIRMED"),
        )
    except LookupError:
        return jsonify({"error": "Shift role not found"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    recalculate_shift_role_capacity(shift_role_id)
    signup["user"] = serialize_signup_user(find_user_by_id(user_id))
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
    is_admin = user_has_role(user_id, "ADMIN")

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
    is_admin = user_has_role(current_user_id, "ADMIN")
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
    """Mark signup attendance as SHOW_UP or NO_SHOW (PANTRY_LEAD for pantry or ADMIN)."""
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
    """Update signup status (ADMIN only)."""
    user = current_user()
    if not user or not user_has_role(int(user.get("user_id")), "ADMIN"):
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
    app.run(debug=True, port=5000)
