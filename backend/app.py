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


@app.before_request
def set_current_user() -> None:
    """Allow switching user via ?user_id=X query parameter for testing."""
    user_id = request.args.get("user_id", type=int) or DEFAULT_USER_ID
    g.current_user_id = user_id


def validation_expiration(shift_end_time): 
    current_end_time = datetime.strptime(shift_end_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    current_date_time = datetime.now(timezone.utc)

    if current_date_time > shift_end_time :
        return False 
    return True 


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


def get_shift_roles(shift_id: int) -> list[dict[str, Any]]:
    return backend.list_shift_roles(shift_id)


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
    return jsonify(signups)


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
    """Get all shifts for a pantry (public - no authorization required)."""
    shifts = backend.list_shifts_by_pantry(pantry_id, include_cancelled=True)
    current_date_time = datetime.now(timezone.utc)
    for shift in shifts:
        shift_end_time = shift["end_time"]
        if not validation_expiration(shift_end_time) :
             continue 
        shift["roles"] = get_shift_roles(int(shift.get("shift_id")))
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
    """Get a single shift with its roles (public - no authorization required)."""
    shift = backend.get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Not found"}), 404

    shift["roles"] = get_shift_roles(shift_id)
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
    
    shift_end_time = shift.get("end_time")


    if validation_expiration(shift_end_time) :
        return jsonify({"error": "Expiration Shift"}), 403


    if not is_admin and not backend.is_pantry_lead(pantry_id, user_id):
        return jsonify({"error": "Forbidden"}), 403

    roles_with_signups: list[dict[str, Any]] = []
    for role in get_shift_roles(shift_id):
        role_id = int(role.get("shift_role_id"))
        signups = get_shift_signups(role_id)

        enriched_signups: list[dict[str, Any]] = []
        for signup in signups:
            signup_with_user = dict(signup)
            signup_user = find_user_by_id(int(signup.get("user_id")))
            signup_with_user["user"] = serialize_signup_user(signup_user)
            enriched_signups.append(signup_with_user)

        role_with_signups = dict(role)
        role_with_signups["signups"] = enriched_signups
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
    is_admin = user_has_role(user_id, "ADMIN")
    pantry_id = int(shift.get("pantry_id"))

    if not is_admin and not backend.is_pantry_lead(pantry_id, user_id):
        return jsonify({"error": "Forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    updated = backend.update_shift(shift_id, payload)
    if not updated:
        return jsonify({"error": "Not found"}), 404
    updated["roles"] = get_shift_roles(shift_id)
    return jsonify(updated)


@app.delete("/api/shifts/<int:shift_id>")
def delete_shift(shift_id: int) -> Any:
    """Delete a shift (PANTRY_LEAD or ADMIN)."""
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

    backend.delete_shift(shift_id)
    return jsonify({"success": True}), 200


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
    is_admin = user_has_role(user_id, "ADMIN")
    pantry_id = int(shift.get("pantry_id"))

    if not is_admin and not backend.is_pantry_lead(pantry_id, user_id):
        return jsonify({"error": "Forbidden"}), 403

    payload = request.get_json(silent=True) or {}
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
    return jsonify(updated)


@app.delete("/api/shift-roles/<int:shift_role_id>")
def delete_shift_role(shift_role_id: int) -> Any:
    """Delete a shift role and its signups."""
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
    is_admin = user_has_role(user_id, "ADMIN")
    pantry_id = int(shift.get("pantry_id"))

    if not is_admin and not backend.is_pantry_lead(pantry_id, user_id):
        return jsonify({"error": "Forbidden"}), 403

    backend.delete_shift_role(shift_role_id)
    return jsonify({"success": True}), 200


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

    payload = request.get_json(silent=True) or {}
    payload_user_id = payload.get("user_id")

    # Users can only sign themselves up, unless authenticated (future)
    user_id = int(payload_user_id or user.get("user_id"))

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

    signup["user"] = find_user_by_id(user_id)
    return jsonify(signup), 201


@app.get("/api/shift-roles/<int:shift_role_id>/signups")
def get_signups_for_role(shift_role_id: int) -> Any:
    """Get all signups for a shift role."""
    shift_role = backend.get_shift_role_by_id(shift_role_id)
    if not shift_role:
        return jsonify({"error": "Not found"}), 404

    signups = get_shift_signups(shift_role_id)
    for signup in signups:
        signup["user"] = find_user_by_id(int(signup.get("user_id")))

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
        if not validation_expiration(shift["end_time"]) :
            continue
        shift["roles"] = get_shift_roles(int(shift.get("shift_id")))

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
