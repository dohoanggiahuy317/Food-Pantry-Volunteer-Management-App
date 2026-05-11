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
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        self._data_path = data_path or (Path(__file__).resolve().parents[1] / "data" / "in_memory.json")
        self.store: dict[str, list[dict[str, Any]]] = {
            "users": [],
            "roles": [],
            "user_roles": [],
            "pantries": [],
            "pantry_leads": [],
            "pantry_subscriptions": [],
            "shift_series": [],
            "shifts": [],
            "shift_roles": [],
            "shift_signups": [],
            "help_broadcasts": [],
            "google_calendar_connections": [],
            "google_calendar_event_links": [],
        }
        self.next_shift_series_id = 1
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
            "pantry_subscriptions": list(data.get("pantry_subscriptions", [])),
            "shift_series": list(data.get("shift_series", [])),
            "shifts": list(data.get("shifts", [])),
            "shift_roles": list(data.get("shift_roles", [])),
            "shift_signups": list(data.get("shift_signups", [])),
            "help_broadcasts": list(data.get("help_broadcasts", [])),
            "google_calendar_connections": list(data.get("google_calendar_connections", [])),
            "google_calendar_event_links": list(data.get("google_calendar_event_links", [])),
        }
        for user in self.store["users"]:
            user.setdefault("updated_at", user.get("created_at"))
            user.setdefault("timezone", None)
            user.setdefault("auth_provider", None)
            user.setdefault("auth_uid", None)
        if self.store["shift_series"]:
            self.next_shift_series_id = max(ss.get("shift_series_id", 0) for ss in self.store["shift_series"]) + 1
        if self.store["shifts"]:
            self.next_shift_id = max(s.get("shift_id", 0) for s in self.store["shifts"]) + 1
        if self.store["shift_roles"]:
            self.next_shift_role_id = max(sr.get("shift_role_id", 0) for sr in self.store["shift_roles"]) + 1
        if self.store["shift_signups"]:
            self.next_signup_id = max(su.get("signup_id", 0) for su in self.store["shift_signups"]) + 1
        self._recalculate_all_attendance_scores()

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        return self._copy(next((u for u in self.store["users"] if u.get("user_id") == user_id), None))

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        normalized_email = str(email).strip().lower()
        return self._copy(
            next(
                (
                    u
                    for u in self.store["users"]
                    if str(u.get("email", "")).strip().lower() == normalized_email
                ),
                None,
            )
        )

    def get_user_by_auth_uid(self, auth_uid: str) -> dict[str, Any] | None:
        normalized_auth_uid = str(auth_uid).strip()
        if not normalized_auth_uid:
            return None
        return self._copy(
            next(
                (
                    u
                    for u in self.store["users"]
                    if str(u.get("auth_uid", "")).strip() == normalized_auth_uid
                ),
                None,
            )
        )

    def get_role_by_id(self, role_id: int) -> dict[str, Any] | None:
        return self._copy(next((r for r in self.store["roles"] if int(r.get("role_id", -1)) == role_id), None))

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

    def list_help_broadcast_candidates(
        self,
        pantry_id: int,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        normalized_query = str(query or "").strip().lower()
        volunteer_users = self.list_users("VOLUNTEER")

        attended_user_ids: set[int] = set()
        pantry_shift_ids = {
            int(shift.get("shift_id"))
            for shift in self.store.get("shifts", [])
            if int(shift.get("pantry_id", 0)) == pantry_id
        }
        pantry_role_ids = {
            int(role.get("shift_role_id"))
            for role in self.store.get("shift_roles", [])
            if int(role.get("shift_id", 0)) in pantry_shift_ids
        }
        for signup in self.store.get("shift_signups", []):
            if int(signup.get("shift_role_id", 0)) not in pantry_role_ids:
                continue
            if str(signup.get("signup_status", "")).upper() == "SHOW_UP":
                attended_user_ids.add(int(signup.get("user_id", 0)))

        candidates: list[dict[str, Any]] = []
        for user in volunteer_users:
            user_id = int(user.get("user_id", 0))
            full_name = str(user.get("full_name") or "")
            email = str(user.get("email") or "")
            if normalized_query and normalized_query not in full_name.lower() and normalized_query not in email.lower():
                continue
            candidates.append(
                {
                    "user_id": user_id,
                    "full_name": full_name,
                    "email": email,
                    "attendance_score": int(user.get("attendance_score", 100)),
                    "has_attended_pantry": user_id in attended_user_ids,
                }
            )

        candidates.sort(
            key=lambda user: (
                0 if user["has_attended_pantry"] else 1,
                -int(user.get("attendance_score", 0)),
                str(user.get("full_name") or "").lower(),
                int(user.get("user_id", 0)),
            )
        )
        return candidates[: max(0, int(limit))]

    def list_roles(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.store["roles"]]

    def create_user(
        self,
        full_name: str,
        email: str,
        phone_number: str | None,
        roles: list[str],
        timezone: str | None = None,
        auth_provider: str | None = None,
        auth_uid: str | None = None,
    ) -> dict[str, Any]:
        normalized_email = str(email).strip().lower()
        if any(str(u.get("email", "")).strip().lower() == normalized_email for u in self.store["users"]):
            raise ValueError("Email already exists")
        normalized_auth_provider = str(auth_provider).strip() if auth_provider is not None else ""
        normalized_auth_uid = str(auth_uid).strip() if auth_uid is not None else ""
        normalized_auth_provider = normalized_auth_provider or None
        normalized_auth_uid = normalized_auth_uid or None
        if normalized_auth_uid and any(str(u.get("auth_uid", "")).strip() == normalized_auth_uid for u in self.store["users"]):
            raise ValueError("Authentication identity already exists")

        user_id = max((u.get("user_id", 0) for u in self.store["users"]), default=0) + 1
        timestamp = _utc_now_iso()
        new_user = {
            "user_id": user_id,
            "full_name": full_name,
            "email": normalized_email,
            "phone_number": phone_number,
            "timezone": str(timezone).strip() or None if timezone is not None else None,
            "attendance_score": 100,
            "created_at": timestamp,
            "updated_at": timestamp,
            "auth_provider": normalized_auth_provider,
            "auth_uid": normalized_auth_uid,
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

    def update_user(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        user = next((u for u in self.store["users"] if u.get("user_id") == user_id), None)
        if not user:
            return None

        allowed_keys = {"full_name", "email", "phone_number", "timezone", "auth_provider", "auth_uid"}
        updates = {key: value for key, value in payload.items() if key in allowed_keys}
        if not updates:
            return dict(user)

        if "email" in updates:
            normalized_email = str(updates["email"]).strip().lower()
            if any(
                int(existing.get("user_id", 0)) != user_id
                and str(existing.get("email", "")).strip().lower() == normalized_email
                for existing in self.store["users"]
            ):
                raise ValueError("Email already exists")
            updates["email"] = normalized_email

        if "auth_uid" in updates:
            normalized_auth_uid = str(updates["auth_uid"]).strip() if updates["auth_uid"] is not None else ""
            normalized_auth_uid = normalized_auth_uid or None
            if normalized_auth_uid and any(
                int(existing.get("user_id", 0)) != user_id
                and str(existing.get("auth_uid", "")).strip() == normalized_auth_uid
                for existing in self.store["users"]
            ):
                raise ValueError("Authentication identity already exists")
            updates["auth_uid"] = normalized_auth_uid

        if "auth_provider" in updates:
            normalized_auth_provider = str(updates["auth_provider"]).strip() if updates["auth_provider"] is not None else ""
            updates["auth_provider"] = normalized_auth_provider or None

        if "timezone" in updates:
            normalized_timezone = str(updates["timezone"]).strip() if updates["timezone"] is not None else ""
            updates["timezone"] = normalized_timezone or None

        for key, value in updates.items():
            user[key] = value

        user["updated_at"] = _utc_now_iso()
        return dict(user)

    def replace_user_roles(self, user_id: int, role_ids: list[int]) -> list[str] | None:
        user = next((u for u in self.store["users"] if int(u.get("user_id", 0)) == user_id), None)
        if not user:
            return None

        valid_role_ids = {
            int(role.get("role_id"))
            for role in self.store["roles"]
            if role.get("role_id") is not None
        }
        normalized_role_ids: list[int] = []
        seen_role_ids: set[int] = set()
        for role_id in role_ids:
            normalized_role_id = int(role_id)
            if normalized_role_id not in valid_role_ids or normalized_role_id in seen_role_ids:
                continue
            seen_role_ids.add(normalized_role_id)
            normalized_role_ids.append(normalized_role_id)

        self.store["user_roles"] = [
            row for row in self.store["user_roles"] if int(row.get("user_id", 0)) != user_id
        ]
        for role_id in normalized_role_ids:
            self.store["user_roles"].append({
                "user_id": user_id,
                "role_id": role_id,
            })

        user["updated_at"] = _utc_now_iso()
        return self.get_user_roles(user_id)

    def delete_user(self, user_id: int) -> None:
        self.store["users"] = [user for user in self.store["users"] if int(user.get("user_id", 0)) != user_id]
        self.store["user_roles"] = [row for row in self.store["user_roles"] if int(row.get("user_id", 0)) != user_id]
        self.store["pantry_leads"] = [row for row in self.store["pantry_leads"] if int(row.get("user_id", 0)) != user_id]
        self.store["pantry_subscriptions"] = [
            row for row in self.store["pantry_subscriptions"] if int(row.get("user_id", 0)) != user_id
        ]
        self.store["shift_signups"] = [row for row in self.store["shift_signups"] if int(row.get("user_id", 0)) != user_id]
        self.store["google_calendar_connections"] = [
            row for row in self.store.setdefault("google_calendar_connections", []) if int(row.get("user_id", 0)) != user_id
        ]
        self.store["google_calendar_event_links"] = [
            row for row in self.store.setdefault("google_calendar_event_links", []) if int(row.get("user_id", 0)) != user_id
        ]
        for shift in self.store["shifts"]:
            if int(shift.get("created_by", 0)) == user_id:
                shift["created_by"] = None

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
        self.store["pantry_subscriptions"] = [
            row
            for row in self.store["pantry_subscriptions"]
            if int(row.get("pantry_id", 0)) != pantry_id
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

    def list_pantry_subscriptions_for_user(self, user_id: int) -> list[int]:
        return sorted(
            {
                int(row.get("pantry_id", 0))
                for row in self.store["pantry_subscriptions"]
                if int(row.get("user_id", 0)) == user_id
            }
        )

    def is_user_subscribed_to_pantry(self, pantry_id: int, user_id: int) -> bool:
        return any(
            int(row.get("pantry_id", 0)) == pantry_id and int(row.get("user_id", 0)) == user_id
            for row in self.store["pantry_subscriptions"]
        )

    def subscribe_user_to_pantry(self, pantry_id: int, user_id: int) -> None:
        if self.is_user_subscribed_to_pantry(pantry_id, user_id):
            return
        self.store["pantry_subscriptions"].append(
            {
                "pantry_id": pantry_id,
                "user_id": user_id,
                "created_at": _utc_now_iso(),
            }
        )

    def unsubscribe_user_from_pantry(self, pantry_id: int, user_id: int) -> None:
        self.store["pantry_subscriptions"] = [
            row
            for row in self.store["pantry_subscriptions"]
            if not (int(row.get("pantry_id", 0)) == pantry_id and int(row.get("user_id", 0)) == user_id)
        ]

    def list_pantry_subscribers(self, pantry_id: int) -> list[dict[str, Any]]:
        user_ids = [
            int(row.get("user_id", 0))
            for row in self.store["pantry_subscriptions"]
            if int(row.get("pantry_id", 0)) == pantry_id
        ]
        users_by_id = {int(user.get("user_id", 0)): dict(user) for user in self.store["users"]}
        return [users_by_id[user_id] for user_id in user_ids if user_id in users_by_id]

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

    def list_non_expired_shifts_in_range(
        self,
        start_time: str,
        end_time: str,
        include_cancelled: bool = True,
    ) -> list[dict[str, Any]]:
        range_start = _parse_iso_to_utc(start_time)
        range_end = _parse_iso_to_utc(end_time)
        if not range_start or not range_end:
            return []

        now_utc = datetime.now(timezone.utc)
        shifts: list[dict[str, Any]] = []
        for shift in self.store["shifts"]:
            shift_start = _parse_iso_to_utc(shift.get("start_time"))
            shift_end = _parse_iso_to_utc(shift.get("end_time"))
            if not shift_start or not shift_end:
                continue
            if shift_end < now_utc:
                continue
            if shift_end < range_start or shift_start > range_end:
                continue
            if not include_cancelled and str(shift.get("status", "")).upper() == "CANCELLED":
                continue
            shifts.append(dict(shift))

        return sorted(shifts, key=lambda item: (str(item.get("start_time") or ""), int(item.get("shift_id") or 0)))

    def list_shifts_in_range(
        self,
        start_time: str,
        end_time: str,
        include_cancelled: bool = True,
    ) -> list[dict[str, Any]]:
        range_start = _parse_iso_to_utc(start_time)
        range_end = _parse_iso_to_utc(end_time)
        if not range_start or not range_end:
            return []

        shifts: list[dict[str, Any]] = []
        for shift in self.store["shifts"]:
            shift_start = _parse_iso_to_utc(shift.get("start_time"))
            shift_end = _parse_iso_to_utc(shift.get("end_time"))
            if not shift_start or not shift_end:
                continue
            if shift_end < range_start or shift_start > range_end:
                continue
            if not include_cancelled and str(shift.get("status", "")).upper() == "CANCELLED":
                continue
            shifts.append(dict(shift))

        return sorted(shifts, key=lambda item: (str(item.get("start_time") or ""), int(item.get("shift_id") or 0)))

    def get_shift_by_id(self, shift_id: int) -> dict[str, Any] | None:
        return self._copy(next((s for s in self.store["shifts"] if s.get("shift_id") == shift_id), None))

    def list_shifts_by_series(self, shift_series_id: int) -> list[dict[str, Any]]:
        shifts = [
            dict(shift)
            for shift in self.store["shifts"]
            if int(shift.get("shift_series_id") or 0) == shift_series_id
        ]
        return sorted(shifts, key=lambda item: (str(item.get("start_time") or ""), int(item.get("shift_id") or 0)))

    def get_shift_series_by_id(self, shift_series_id: int) -> dict[str, Any] | None:
        return self._copy(next((row for row in self.store["shift_series"] if row.get("shift_series_id") == shift_series_id), None))

    def create_shift_series(self, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = _utc_now_iso()
        series = {
            "shift_series_id": self.next_shift_series_id,
            "pantry_id": int(payload["pantry_id"]),
            "created_by": payload.get("created_by"),
            "timezone": payload["timezone"],
            "frequency": payload.get("frequency", "WEEKLY"),
            "interval_weeks": int(payload.get("interval_weeks", 1)),
            "weekdays_csv": payload["weekdays_csv"],
            "end_mode": payload["end_mode"],
            "occurrence_count": payload.get("occurrence_count"),
            "until_date": payload.get("until_date"),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self.next_shift_series_id += 1
        self.store["shift_series"].append(series)
        return dict(series)

    def update_shift_series(self, shift_series_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        series = next((row for row in self.store["shift_series"] if row.get("shift_series_id") == shift_series_id), None)
        if not series:
            return None
        for key in ["timezone", "frequency", "weekdays_csv", "end_mode", "occurrence_count", "until_date"]:
            if key in payload:
                series[key] = payload[key]
        if "interval_weeks" in payload:
            series["interval_weeks"] = int(payload["interval_weeks"])
        series["updated_at"] = _utc_now_iso()
        return dict(series)

    def create_shift(
        self,
        pantry_id: int,
        shift_name: str,
        start_time: str,
        end_time: str,
        status: str,
        created_by: int,
        shift_series_id: int | None = None,
        series_position: int | None = None,
    ) -> dict[str, Any]:
        timestamp = _utc_now_iso()
        shift = {
            "shift_id": self.next_shift_id,
            "pantry_id": pantry_id,
            "shift_series_id": shift_series_id,
            "series_position": series_position,
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
        for key in ["shift_name", "start_time", "end_time", "status", "shift_series_id", "series_position"]:
            if key in payload:
                shift[key] = payload[key]
        shift["updated_at"] = _utc_now_iso()
        return dict(shift)

    def replace_shift_and_roles(
        self,
        shift_id: int,
        shift_payload: dict[str, Any],
        roles_payload: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        shift = next((s for s in self.store["shifts"] if s.get("shift_id") == shift_id), None)
        if not shift:
            return None

        existing_roles = {
            int(role.get("shift_role_id")): role
            for role in self.store["shift_roles"]
            if int(role.get("shift_id")) == shift_id
        }

        normalized_roles: list[dict[str, Any]] = []
        seen_role_ids: set[int] = set()
        for payload in roles_payload:
            role_title = str(payload.get("role_title") or "").strip()
            if not role_title:
                raise ValueError("role_title is required")

            try:
                required_count = int(payload.get("required_count"))
            except (TypeError, ValueError) as exc:
                raise ValueError("required_count must be >= 1") from exc
            if required_count < 1:
                raise ValueError("required_count must be >= 1")

            raw_role_id = payload.get("shift_role_id")
            role_id = int(raw_role_id) if raw_role_id is not None else None
            if role_id is not None:
                if role_id in seen_role_ids:
                    raise ValueError("Duplicate shift_role_id in roles payload")
                if role_id not in existing_roles:
                    raise ValueError("Shift role not found for this shift")
                seen_role_ids.add(role_id)

            normalized_roles.append({
                "shift_role_id": role_id,
                "role_title": role_title,
                "required_count": required_count,
            })

        for key in ["shift_name", "start_time", "end_time", "status", "shift_series_id", "series_position"]:
            if key in shift_payload:
                shift[key] = shift_payload[key]
        shift["updated_at"] = _utc_now_iso()

        submitted_existing_ids: set[int] = set()
        for payload in normalized_roles:
            role_id = payload.get("shift_role_id")
            if role_id is not None:
                submitted_existing_ids.add(int(role_id))
                role = existing_roles[int(role_id)]
                role["role_title"] = payload["role_title"]
                role["required_count"] = payload["required_count"]
                continue

            role = {
                "shift_role_id": self.next_shift_role_id,
                "shift_id": shift_id,
                "role_title": payload["role_title"],
                "required_count": payload["required_count"],
                "filled_count": 0,
                "status": "OPEN",
            }
            self.next_shift_role_id += 1
            self.store["shift_roles"].append(role)

        omitted_role_ids = set(existing_roles) - submitted_existing_ids
        roles_to_delete: set[int] = set()
        for role_id in omitted_role_ids:
            has_signups = any(
                int(signup.get("shift_role_id")) == role_id
                for signup in self.store["shift_signups"]
            )
            if has_signups:
                role = existing_roles[role_id]
                role["status"] = "CANCELLED"
                role["filled_count"] = 0
                continue
            roles_to_delete.add(role_id)

        if roles_to_delete:
            self.store["shift_roles"] = [
                role
                for role in self.store["shift_roles"]
                if int(role.get("shift_role_id")) not in roles_to_delete
            ]

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

    def get_latest_help_broadcast_for_sender(self, sender_user_id: int) -> dict[str, Any] | None:
        broadcasts = [
            row
            for row in self.store.setdefault("help_broadcasts", [])
            if int(row.get("sender_user_id", 0)) == sender_user_id
        ]
        if not broadcasts:
            return None
        latest = max(
            broadcasts,
            key=lambda row: _parse_iso_to_utc(row.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
        )
        return dict(latest)

    def create_help_broadcast(self, shift_id: int, sender_user_id: int, recipient_count: int) -> dict[str, Any]:
        broadcasts = self.store.setdefault("help_broadcasts", [])
        broadcast_id = max((int(row.get("broadcast_id", 0)) for row in broadcasts), default=0) + 1
        row = {
            "broadcast_id": broadcast_id,
            "shift_id": shift_id,
            "sender_user_id": sender_user_id,
            "recipient_count": recipient_count,
            "created_at": _utc_now_iso(),
        }
        broadcasts.append(row)
        return dict(row)

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
        self.store["google_calendar_event_links"] = [
            row for row in self.store.setdefault("google_calendar_event_links", []) if int(row.get("signup_id", 0)) != signup_id
        ]
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

    def get_google_calendar_connection(self, user_id: int) -> dict[str, Any] | None:
        return self._copy(
            next(
                (
                    row
                    for row in self.store.setdefault("google_calendar_connections", [])
                    if int(row.get("user_id", 0)) == user_id
                ),
                None,
            )
        )

    def upsert_google_calendar_connection(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = _utc_now_iso()
        row = next(
            (
                existing
                for existing in self.store.setdefault("google_calendar_connections", [])
                if int(existing.get("user_id", 0)) == user_id
            ),
            None,
        )
        if row:
            for key, value in payload.items():
                if key == "refresh_token" and value is None:
                    continue
                row[key] = value
            row["updated_at"] = timestamp
            return dict(row)

        row = {"user_id": user_id, "created_at": timestamp, "updated_at": timestamp, **payload}
        self.store.setdefault("google_calendar_connections", []).append(row)
        return dict(row)

    def delete_google_calendar_connection(self, user_id: int) -> None:
        self.store["google_calendar_connections"] = [
            row for row in self.store.setdefault("google_calendar_connections", []) if int(row.get("user_id", 0)) != user_id
        ]

    def get_google_calendar_event_link(self, signup_id: int) -> dict[str, Any] | None:
        return self._copy(
            next(
                (
                    row
                    for row in self.store.setdefault("google_calendar_event_links", [])
                    if int(row.get("signup_id", 0)) == signup_id
                ),
                None,
            )
        )

    def upsert_google_calendar_event_link(self, signup_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = _utc_now_iso()
        row = next(
            (
                existing
                for existing in self.store.setdefault("google_calendar_event_links", [])
                if int(existing.get("signup_id", 0)) == signup_id
            ),
            None,
        )
        if row:
            row.update(payload)
            row["updated_at"] = timestamp
            return dict(row)

        row = {"signup_id": signup_id, "created_at": timestamp, "updated_at": timestamp, **payload}
        self.store.setdefault("google_calendar_event_links", []).append(row)
        return dict(row)

    def delete_google_calendar_event_link(self, signup_id: int) -> None:
        self.store["google_calendar_event_links"] = [
            row for row in self.store.setdefault("google_calendar_event_links", []) if int(row.get("signup_id", 0)) != signup_id
        ]

    def delete_google_calendar_event_links(self, signup_ids: list[int]) -> None:
        normalized_ids = {int(signup_id) for signup_id in signup_ids if signup_id is not None}
        if not normalized_ids:
            return
        self.store["google_calendar_event_links"] = [
            row
            for row in self.store.setdefault("google_calendar_event_links", [])
            if int(row.get("signup_id", 0)) not in normalized_ids
        ]

    def is_empty(self) -> bool:
        return not self.store["users"] and not self.store["roles"]
