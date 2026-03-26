from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backends.base import StoreBackend

ACTIVE_SIGNUP_STATUSES = {"CONFIRMED", "SHOW_UP", "NO_SHOW"}
PENDING_SIGNUP_STATUS = "PENDING_CONFIRMATION"
RESERVATION_WINDOW_HOURS = 48


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _parse_iso_to_utc(value: Any) -> datetime | None:
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


class MemoryBackend(StoreBackend):
    def __init__(self, data_path: Path | None = None) -> None:
        self._data_path = data_path or (Path(__file__).resolve().parents[1] / "data" / "db.json")
        self.store: dict[str, list[dict[str, Any]]] = {
            "users": [],
            "roles": [],
            "user_roles": [],
            "pantries": [],
            "pantry_leads": [],
            "shifts": [],
            "shift_roles": [],
            "shift_signups": [],
        }
        self.next_shift_id = 1
        self.next_shift_role_id = 1
        self.next_signup_id = 1
        self._load_seed_data()

    def _copy(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def _recalculate_role_capacity(self, shift_role_id: int) -> None:
        role = next((sr for sr in self.store["shift_roles"] if sr.get("shift_role_id") == shift_role_id), None)
        if not role:
            return

        now_utc = datetime.now(timezone.utc)
        active_count = 0
        for signup in self.store["shift_signups"]:
            if signup.get("shift_role_id") != shift_role_id:
                continue
            status = str(signup.get("signup_status", "")).upper()
            reservation_expires_at = _parse_iso_to_utc(signup.get("reservation_expires_at"))
            if status in ACTIVE_SIGNUP_STATUSES or (
                status == PENDING_SIGNUP_STATUS
                and reservation_expires_at is not None
                and reservation_expires_at > now_utc
            ):
                active_count += 1

        role["filled_count"] = active_count
        if str(role.get("status", "OPEN")).upper() == "CANCELLED":
            return
        role["status"] = "FULL" if active_count >= int(role.get("required_count", 0)) else "OPEN"

    def _calculate_user_attendance_score(self, user_id: int) -> int:
        attended_count = 0
        marked_count = 0
        for signup in self.store["shift_signups"]:
            if int(signup.get("user_id", 0)) != user_id:
                continue
            status = str(signup.get("signup_status", "")).upper()
            if status == "SHOW_UP":
                attended_count += 1
            if status in {"SHOW_UP", "NO_SHOW"}:
                marked_count += 1

        if marked_count == 0:
            return 100
        return round((attended_count * 100) / marked_count)

    def _recalculate_user_attendance_score(self, user_id: int) -> None:
        user = next((u for u in self.store["users"] if int(u.get("user_id", 0)) == user_id), None)
        if not user:
            return
        user["attendance_score"] = self._calculate_user_attendance_score(user_id)

    def _recalculate_all_attendance_scores(self) -> None:
        for user in self.store["users"]:
            user["attendance_score"] = self._calculate_user_attendance_score(int(user.get("user_id", 0)))

    def _load_seed_data(self) -> None:
        if not self._data_path.exists():
            return

        data = json.loads(self._data_path.read_text(encoding="utf-8"))
        self.store = {
            "users": list(data.get("users", [])),
            "roles": list(data.get("roles", [])),
            "user_roles": list(data.get("user_roles", [])),
            "pantries": list(data.get("pantries", [])),
            "pantry_leads": list(data.get("pantry_leads", [])),
            "shifts": list(data.get("shifts", [])),
            "shift_roles": list(data.get("shift_roles", [])),
            "shift_signups": list(data.get("shift_signups", [])),
        }
        if self.store["shifts"]:
            self.next_shift_id = max(s.get("shift_id", 0) for s in self.store["shifts"]) + 1
        if self.store["shift_roles"]:
            self.next_shift_role_id = max(sr.get("shift_role_id", 0) for sr in self.store["shift_roles"]) + 1
        if self.store["shift_signups"]:
            self.next_signup_id = max(su.get("signup_id", 0) for su in self.store["shift_signups"]) + 1
        self._recalculate_all_attendance_scores()

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        return self._copy(next((u for u in self.store["users"] if u.get("user_id") == user_id), None))

    def get_user_roles(self, user_id: int) -> list[str]:
        role_ids = [
            ur.get("role_id")
            for ur in self.store["user_roles"]
            if ur.get("user_id") == user_id
        ]
        return [
            r.get("role_name")
            for r in self.store["roles"]
            if r.get("role_id") in role_ids
        ]

    def list_users(self, role_filter: str | None = None) -> list[dict[str, Any]]:
        users = [dict(u) for u in self.store["users"]]
        if role_filter:
            users = [u for u in users if role_filter in self.get_user_roles(u.get("user_id"))]
        return users

    def list_roles(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.store["roles"]]

    def create_user(
        self,
        full_name: str,
        email: str,
        password_hash: str,
        is_active: bool,
        roles: list[str],
    ) -> dict[str, Any]:
        if any(u.get("email") == email for u in self.store["users"]):
            raise ValueError("Email already exists")

        user_id = max((u.get("user_id", 0) for u in self.store["users"]), default=0) + 1
        timestamp = _utc_now_iso()
        new_user = {
            "user_id": user_id,
            "full_name": full_name,
            "email": email,
            "password_hash": password_hash,
            "is_active": is_active,
            "attendance_score": 100,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self.store["users"].append(new_user)

        assigned_roles: list[str] = []
        for role_name in roles:
            role = next((r for r in self.store["roles"] if r.get("role_name") == role_name), None)
            if not role:
                continue
            self.store["user_roles"].append({
                "user_id": user_id,
                "role_id": role.get("role_id"),
            })
            assigned_roles.append(role_name)

        response = dict(new_user)
        response["roles"] = assigned_roles
        return response

    def list_pantries(self) -> list[dict[str, Any]]:
        return [dict(p) for p in self.store["pantries"]]

    def get_pantry_by_id(self, pantry_id: int) -> dict[str, Any] | None:
        return self._copy(next((p for p in self.store["pantries"] if p.get("pantry_id") == pantry_id), None))

    def get_pantry_by_slug(self, slug: str) -> dict[str, Any] | None:
        pantry = next(
            (
                p
                for p in self.store["pantries"]
                if str(p.get("pantry_id")) == slug
                or p.get("name", "").lower().replace(" ", "-") == slug
            ),
            None,
        )
        return self._copy(pantry)

    def get_pantry_leads(self, pantry_id: int) -> list[dict[str, Any]]:
        lead_ids = [pl.get("user_id") for pl in self.store["pantry_leads"] if pl.get("pantry_id") == pantry_id]
        return [dict(u) for u in self.store["users"] if u.get("user_id") in lead_ids]

    def is_pantry_lead(self, pantry_id: int, user_id: int) -> bool:
        return any(
            pl.get("pantry_id") == pantry_id and pl.get("user_id") == user_id
            for pl in self.store["pantry_leads"]
        )

    def create_pantry(self, name: str, location_address: str, lead_ids: list[int]) -> dict[str, Any]:
        pantry_id = max((p.get("pantry_id", 0) for p in self.store["pantries"]), default=0) + 1
        timestamp = _utc_now_iso()
        pantry = {
            "pantry_id": pantry_id,
            "name": name,
            "location_address": location_address,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self.store["pantries"].append(pantry)

        for lead_id in lead_ids:
            if not self.get_user_by_id(lead_id):
                continue
            if "PANTRY_LEAD" not in self.get_user_roles(lead_id):
                continue
            if self.is_pantry_lead(pantry_id, lead_id):
                continue
            self.store["pantry_leads"].append({"pantry_id": pantry_id, "user_id": lead_id})

        response = dict(pantry)
        response["leads"] = self.get_pantry_leads(pantry_id)
        return response

    def update_pantry(self, pantry_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        pantry = next((p for p in self.store["pantries"] if p.get("pantry_id") == pantry_id), None)
        if not pantry:
            return None
        for key in ["name", "location_address"]:
            if key in payload:
                pantry[key] = payload[key]
        pantry["updated_at"] = _utc_now_iso()
        return dict(pantry)

    def delete_pantry(self, pantry_id: int) -> None:
        shift_ids = [shift.get("shift_id") for shift in self.store["shifts"] if shift.get("pantry_id") == pantry_id]
        shift_role_ids = [
            role.get("shift_role_id")
            for role in self.store["shift_roles"]
            if role.get("shift_id") in shift_ids
        ]

        self.store["shift_signups"] = [
            signup
            for signup in self.store["shift_signups"]
            if signup.get("shift_role_id") not in shift_role_ids
        ]
        self.store["shift_roles"] = [
            role
            for role in self.store["shift_roles"]
            if role.get("shift_id") not in shift_ids
        ]
        self.store["shifts"] = [
            shift
            for shift in self.store["shifts"]
            if shift.get("pantry_id") != pantry_id
        ]
        self.store["pantry_leads"] = [
            pantry_lead
            for pantry_lead in self.store["pantry_leads"]
            if pantry_lead.get("pantry_id") != pantry_id
        ]
        self.store["pantries"] = [
            pantry
            for pantry in self.store["pantries"]
            if pantry.get("pantry_id") != pantry_id
        ]

    def add_pantry_lead(self, pantry_id: int, user_id: int) -> None:
        if self.is_pantry_lead(pantry_id, user_id):
            raise ValueError("User already a lead for this pantry")
        self.store["pantry_leads"].append({"pantry_id": pantry_id, "user_id": user_id})

    def remove_pantry_lead(self, pantry_id: int, user_id: int) -> None:
        self.store["pantry_leads"] = [
            pl
            for pl in self.store["pantry_leads"]
            if not (pl.get("pantry_id") == pantry_id and pl.get("user_id") == user_id)
        ]

    def list_shifts_by_pantry(self, pantry_id: int, include_cancelled: bool = True) -> list[dict[str, Any]]:
        shifts = [dict(s) for s in self.store["shifts"] if s.get("pantry_id") == pantry_id]
        if not include_cancelled:
            shifts = [s for s in shifts if str(s.get("status", "")).upper() != "CANCELLED"]
        return shifts

    def list_non_expired_shifts_by_pantry(
        self,
        pantry_id: int,
        include_cancelled: bool = True,
    ) -> list[dict[str, Any]]:
        shifts = [dict(s) for s in self.store["shifts"] if s.get("pantry_id") == pantry_id]
        now_utc = datetime.now(timezone.utc)
        shifts = [s for s in shifts if (end_time := _parse_iso_to_utc(s.get("end_time"))) and end_time >= now_utc]
        if not include_cancelled:
            shifts = [s for s in shifts if str(s.get("status", "")).upper() != "CANCELLED"]
        return shifts

    def get_shift_by_id(self, shift_id: int) -> dict[str, Any] | None:
        return self._copy(next((s for s in self.store["shifts"] if s.get("shift_id") == shift_id), None))

    def create_shift(
        self,
        pantry_id: int,
        shift_name: str,
        start_time: str,
        end_time: str,
        status: str,
        created_by: int,
    ) -> dict[str, Any]:
        timestamp = _utc_now_iso()
        shift = {
            "shift_id": self.next_shift_id,
            "pantry_id": pantry_id,
            "shift_name": shift_name,
            "start_time": start_time,
            "end_time": end_time,
            "status": status,
            "created_by": created_by,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self.next_shift_id += 1
        self.store["shifts"].append(shift)
        return dict(shift)

    def update_shift(self, shift_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        shift = next((s for s in self.store["shifts"] if s.get("shift_id") == shift_id), None)
        if not shift:
            return None
        for key in ["shift_name", "start_time", "end_time", "status"]:
            if key in payload:
                shift[key] = payload[key]
        shift["updated_at"] = _utc_now_iso()
        return dict(shift)

    def delete_shift(self, shift_id: int) -> None:
        shift_role_ids = [sr.get("shift_role_id") for sr in self.store["shift_roles"] if sr.get("shift_id") == shift_id]
        self.store["shift_signups"] = [
            ss for ss in self.store["shift_signups"] if ss.get("shift_role_id") not in shift_role_ids
        ]
        self.store["shift_roles"] = [sr for sr in self.store["shift_roles"] if sr.get("shift_id") != shift_id]
        self.store["shifts"] = [s for s in self.store["shifts"] if s.get("shift_id") != shift_id]

    def list_shift_roles(self, shift_id: int) -> list[dict[str, Any]]:
        return [dict(sr) for sr in self.store["shift_roles"] if sr.get("shift_id") == shift_id]

    def get_shift_role_by_id(self, shift_role_id: int) -> dict[str, Any] | None:
        return self._copy(next((sr for sr in self.store["shift_roles"] if sr.get("shift_role_id") == shift_role_id), None))

    def create_shift_role(self, shift_id: int, role_title: str, required_count: int) -> dict[str, Any]:
        role = {
            "shift_role_id": self.next_shift_role_id,
            "shift_id": shift_id,
            "role_title": role_title,
            "required_count": required_count,
            "filled_count": 0,
            "status": "OPEN",
        }
        self.next_shift_role_id += 1
        self.store["shift_roles"].append(role)
        return dict(role)

    def update_shift_role(self, shift_role_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        role = next((sr for sr in self.store["shift_roles"] if sr.get("shift_role_id") == shift_role_id), None)
        if not role:
            return None
        for key in ["role_title", "required_count", "status", "filled_count"]:
            if key in payload:
                role[key] = payload[key]
        if "required_count" in payload or "status" in payload:
            self._recalculate_role_capacity(shift_role_id)
        return dict(role)

    def delete_shift_role(self, shift_role_id: int) -> None:
        self.store["shift_signups"] = [ss for ss in self.store["shift_signups"] if ss.get("shift_role_id") != shift_role_id]
        self.store["shift_roles"] = [sr for sr in self.store["shift_roles"] if sr.get("shift_role_id") != shift_role_id]

    def list_shift_signups(self, shift_role_id: int) -> list[dict[str, Any]]:
        return [dict(ss) for ss in self.store["shift_signups"] if ss.get("shift_role_id") == shift_role_id]

    def list_signups_by_user(self, user_id: int) -> list[dict[str, Any]]:
        signups = [dict(ss) for ss in self.store["shift_signups"] if ss.get("user_id") == user_id]
        rows: list[dict[str, Any]] = []

        for signup in signups:
            shift_role_id = int(signup.get("shift_role_id"))
            role = next((sr for sr in self.store["shift_roles"] if sr.get("shift_role_id") == shift_role_id), None)
            if not role:
                continue

            shift_id = int(role.get("shift_id"))
            shift = next((s for s in self.store["shifts"] if s.get("shift_id") == shift_id), None)
            if not shift:
                continue

            pantry_id = int(shift.get("pantry_id"))
            pantry = next((p for p in self.store["pantries"] if p.get("pantry_id") == pantry_id), None)

            rows.append({
                "signup_id": int(signup.get("signup_id")),
                "user_id": int(signup.get("user_id")),
                "signup_status": signup.get("signup_status"),
                "reservation_expires_at": signup.get("reservation_expires_at"),
                "created_at": signup.get("created_at"),
                "shift_role_id": int(role.get("shift_role_id")),
                "role_title": role.get("role_title"),
                "required_count": int(role.get("required_count", 0)),
                "filled_count": int(role.get("filled_count", 0)),
                "role_status": role.get("status"),
                "shift_id": int(shift.get("shift_id")),
                "shift_name": shift.get("shift_name"),
                "start_time": shift.get("start_time"),
                "end_time": shift.get("end_time"),
                "shift_status": shift.get("status"),
                "pantry_id": int(shift.get("pantry_id")),
                "pantry_name": pantry.get("name") if pantry else None,
                "pantry_location": pantry.get("location_address") if pantry else None,
            })

        rows.sort(key=lambda row: str(row.get("start_time", "")))
        return rows

    def get_signup_by_id(self, signup_id: int) -> dict[str, Any] | None:
        return self._copy(next((ss for ss in self.store["shift_signups"] if ss.get("signup_id") == signup_id), None))

    def create_signup(self, shift_role_id: int, user_id: int, signup_status: str) -> dict[str, Any]:
        shift_role = next((sr for sr in self.store["shift_roles"] if sr.get("shift_role_id") == shift_role_id), None)
        if not shift_role:
            raise LookupError("Shift role not found")
        if str(shift_role.get("status", "OPEN")).upper() == "CANCELLED":
            raise RuntimeError("This role is unavailable")

        shift = next((s for s in self.store["shifts"] if s.get("shift_id") == int(shift_role.get("shift_id"))), None)
        if not shift:
            raise LookupError("Shift not found")
        if str(shift.get("status", "OPEN")).upper() == "CANCELLED":
            raise RuntimeError("This shift is cancelled")

        if any(
            ss.get("shift_role_id") == shift_role_id and ss.get("user_id") == user_id
            for ss in self.store["shift_signups"]
        ):
            raise ValueError("Already signed up")

        self._recalculate_role_capacity(shift_role_id)
        now_utc = datetime.now(timezone.utc)
        occupied_count = 0
        for signup in self.store["shift_signups"]:
            if signup.get("shift_role_id") != shift_role_id:
                continue
            status = str(signup.get("signup_status", "")).upper()
            reservation_expires_at = _parse_iso_to_utc(signup.get("reservation_expires_at"))
            if status in ACTIVE_SIGNUP_STATUSES or (
                status == PENDING_SIGNUP_STATUS
                and reservation_expires_at is not None
                and reservation_expires_at > now_utc
            ):
                occupied_count += 1

        if occupied_count >= int(shift_role.get("required_count", 0)):
            raise RuntimeError("This role is full")

        signup = {
            "signup_id": self.next_signup_id,
            "shift_role_id": shift_role_id,
            "user_id": user_id,
            "signup_status": signup_status,
            "reservation_expires_at": (
                (datetime.now(timezone.utc) + timedelta(hours=RESERVATION_WINDOW_HOURS)).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
                if str(signup_status).upper() == PENDING_SIGNUP_STATUS
                else None
            ),
            "created_at": _utc_now_iso(),
        }
        self.next_signup_id += 1
        self.store["shift_signups"].append(signup)
        self._recalculate_role_capacity(shift_role_id)
        self._recalculate_user_attendance_score(user_id)

        return dict(signup)

    def delete_signup(self, signup_id: int) -> None:
        signup = next((ss for ss in self.store["shift_signups"] if ss.get("signup_id") == signup_id), None)
        if not signup:
            return

        shift_role_id = signup.get("shift_role_id")
        user_id = int(signup.get("user_id"))
        self.store["shift_signups"] = [ss for ss in self.store["shift_signups"] if ss.get("signup_id") != signup_id]
        self._recalculate_role_capacity(int(shift_role_id))
        self._recalculate_user_attendance_score(user_id)

    def update_signup(self, signup_id: int, signup_status: str) -> dict[str, Any] | None:
        signup = next((ss for ss in self.store["shift_signups"] if ss.get("signup_id") == signup_id), None)
        if not signup:
            return None
        user_id = int(signup.get("user_id"))
        signup["signup_status"] = signup_status
        signup["reservation_expires_at"] = (
            (datetime.now(timezone.utc) + timedelta(hours=RESERVATION_WINDOW_HOURS)).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            if str(signup_status).upper() == PENDING_SIGNUP_STATUS
            else None
        )
        self._recalculate_role_capacity(int(signup.get("shift_role_id")))
        self._recalculate_user_attendance_score(user_id)
        return dict(signup)

    def bulk_mark_shift_signups_pending(self, shift_id: int, reservation_expires_at: str) -> list[dict[str, Any]]:
        reservation_iso = _parse_iso_to_utc(reservation_expires_at)
        if not reservation_iso:
            reservation_value = _utc_now_iso()
        else:
            reservation_value = reservation_iso.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

        shift_role_ids = [int(role.get("shift_role_id")) for role in self.store["shift_roles"] if int(role.get("shift_id")) == shift_id]
        affected: list[dict[str, Any]] = []

        for signup in self.store["shift_signups"]:
            if int(signup.get("shift_role_id")) not in shift_role_ids:
                continue
            current_status = str(signup.get("signup_status", "")).upper()
            if current_status in {"CANCELLED", "WAITLISTED"}:
                continue
            signup["signup_status"] = PENDING_SIGNUP_STATUS
            signup["reservation_expires_at"] = reservation_value
            affected.append(
                {
                    "signup_id": int(signup.get("signup_id")),
                    "user_id": int(signup.get("user_id")),
                }
            )

        for role_id in shift_role_ids:
            self._recalculate_role_capacity(role_id)
        return affected

    def expire_pending_signups(self, shift_id: int, now_utc: str) -> int:
        now_dt = _parse_iso_to_utc(now_utc) or datetime.now(timezone.utc)
        shift_role_ids = [int(role.get("shift_role_id")) for role in self.store["shift_roles"] if int(role.get("shift_id")) == shift_id]
        shift = self.get_shift_by_id(shift_id)
        shift_start = _parse_iso_to_utc(shift.get("start_time")) if shift else None

        expired_count = 0
        for signup in self.store["shift_signups"]:
            if int(signup.get("shift_role_id")) not in shift_role_ids:
                continue
            if str(signup.get("signup_status", "")).upper() != PENDING_SIGNUP_STATUS:
                continue
            reservation_expires_at = _parse_iso_to_utc(signup.get("reservation_expires_at"))
            should_expire = (
                (shift_start is not None and shift_start <= now_dt)
                or (reservation_expires_at is not None and reservation_expires_at <= now_dt)
            )
            if not should_expire:
                continue
            signup["signup_status"] = "CANCELLED"
            signup["reservation_expires_at"] = None
            expired_count += 1

        if expired_count:
            for role_id in shift_role_ids:
                self._recalculate_role_capacity(role_id)
        return expired_count

    def reconfirm_pending_signup(self, signup_id: int, now_utc: str) -> dict[str, Any]:
        now_dt = _parse_iso_to_utc(now_utc) or datetime.now(timezone.utc)
        signup = next((ss for ss in self.store["shift_signups"] if ss.get("signup_id") == signup_id), None)
        if not signup:
            return {"result": "NOT_FOUND", "signup": None}

        if str(signup.get("signup_status", "")).upper() != PENDING_SIGNUP_STATUS:
            return {"result": "NOT_PENDING", "signup": dict(signup)}

        shift_role_id = int(signup.get("shift_role_id"))
        shift_role = next((sr for sr in self.store["shift_roles"] if int(sr.get("shift_role_id")) == shift_role_id), None)
        if not shift_role:
            return {"result": "NOT_FOUND", "signup": None}

        shift = next((s for s in self.store["shifts"] if int(s.get("shift_id")) == int(shift_role.get("shift_id"))), None)
        if not shift:
            return {"result": "NOT_FOUND", "signup": None}

        shift_start = _parse_iso_to_utc(shift.get("start_time"))
        reservation_expires_at = _parse_iso_to_utc(signup.get("reservation_expires_at"))
        if (shift_start and shift_start <= now_dt) or (
            reservation_expires_at is not None and reservation_expires_at <= now_dt
        ):
            signup["signup_status"] = "CANCELLED"
            signup["reservation_expires_at"] = None
            self._recalculate_role_capacity(shift_role_id)
            self._recalculate_user_attendance_score(int(signup.get("user_id")))
            return {"result": "EXPIRED", "signup": dict(signup)}

        if (
            str(shift.get("status", "OPEN")).upper() == "CANCELLED"
            or str(shift_role.get("status", "OPEN")).upper() == "CANCELLED"
        ):
            signup["signup_status"] = "WAITLISTED"
            signup["reservation_expires_at"] = None
            self._recalculate_role_capacity(shift_role_id)
            self._recalculate_user_attendance_score(int(signup.get("user_id")))
            return {"result": "WAITLISTED", "signup": dict(signup)}

        confirmed_count = 0
        for other in self.store["shift_signups"]:
            if int(other.get("shift_role_id")) != shift_role_id:
                continue
            if str(other.get("signup_status", "")).upper() in ACTIVE_SIGNUP_STATUSES:
                confirmed_count += 1

        if confirmed_count >= int(shift_role.get("required_count", 0)):
            signup["signup_status"] = "WAITLISTED"
            signup["reservation_expires_at"] = None
            self._recalculate_role_capacity(shift_role_id)
            self._recalculate_user_attendance_score(int(signup.get("user_id")))
            return {"result": "WAITLISTED", "signup": dict(signup)}

        signup["signup_status"] = "CONFIRMED"
        signup["reservation_expires_at"] = None
        self._recalculate_role_capacity(shift_role_id)
        self._recalculate_user_attendance_score(int(signup.get("user_id")))
        return {"result": "CONFIRMED", "signup": dict(signup)}

    def is_empty(self) -> bool:
        return not self.store["users"] and not self.store["roles"]
