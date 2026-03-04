from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from mysql.connector import IntegrityError

from backends.base import StoreBackend
from db.mysql import get_connection

ACTIVE_SIGNUP_STATUSES = ("CONFIRMED", "SHOW_UP", "NO_SHOW")


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_iso_to_dt(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _to_iso_z(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    if isinstance(value, str):
        return value
    return ""


def _serialize_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "password_hash": row["password_hash"],
        "is_active": bool(row["is_active"]),
        "created_at": _to_iso_z(row["created_at"]),
        "updated_at": _to_iso_z(row["updated_at"]),
    }


def _serialize_pantry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pantry_id": row["pantry_id"],
        "name": row["name"],
        "location_address": row["location_address"],
        "created_at": _to_iso_z(row["created_at"]),
        "updated_at": _to_iso_z(row["updated_at"]),
    }


def _serialize_shift(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "shift_id": row["shift_id"],
        "pantry_id": row["pantry_id"],
        "shift_name": row["shift_name"],
        "start_time": _to_iso_z(row["start_time"]),
        "end_time": _to_iso_z(row["end_time"]),
        "status": row["status"],
        "created_by": row["created_by"],
        "created_at": _to_iso_z(row["created_at"]),
        "updated_at": _to_iso_z(row["updated_at"]),
    }


def _serialize_shift_role(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "shift_role_id": row["shift_role_id"],
        "shift_id": row["shift_id"],
        "role_title": row["role_title"],
        "required_count": int(row["required_count"]),
        "filled_count": int(row["filled_count"]),
        "status": row["status"],
    }


def _serialize_signup(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "signup_id": row["signup_id"],
        "shift_role_id": row["shift_role_id"],
        "user_id": row["user_id"],
        "signup_status": row["signup_status"],
        "created_at": _to_iso_z(row["created_at"]),
    }


class MySQLBackend(StoreBackend):
    def _recalculate_role_capacity(self, cursor: Any, shift_role_id: int) -> None:
        cursor.execute(
            "SELECT required_count, status FROM shift_roles WHERE shift_role_id = %s FOR UPDATE",
            (shift_role_id,),
        )
        role_row = cursor.fetchone()
        if not role_row:
            return

        cursor.execute(
            """
            SELECT COUNT(*) AS active_count
            FROM shift_signups
            WHERE shift_role_id = %s
              AND UPPER(signup_status) IN ('CONFIRMED', 'SHOW_UP', 'NO_SHOW')
            """,
            (shift_role_id,),
        )
        active_count = int(cursor.fetchone()["active_count"])
        required_count = int(role_row["required_count"])
        role_status = str(role_row["status"]).upper()
        if role_status == "CANCELLED":
            next_status = "CANCELLED"
        else:
            next_status = "FULL" if active_count >= required_count else "OPEN"

        cursor.execute(
            "UPDATE shift_roles SET filled_count = %s, status = %s WHERE shift_role_id = %s",
            (active_count, next_status, shift_role_id),
        )

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            return _serialize_user(row) if row else None

    def get_user_roles(self, user_id: int) -> list[str]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT r.role_name
                FROM user_roles ur
                JOIN roles r ON r.role_id = ur.role_id
                WHERE ur.user_id = %s
                ORDER BY r.role_id
                """,
                (user_id,),
            )
            return [row["role_name"] for row in cursor.fetchall()]

    def list_users(self, role_filter: str | None = None) -> list[dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            if role_filter:
                cursor.execute(
                    """
                    SELECT DISTINCT u.*
                    FROM users u
                    JOIN user_roles ur ON ur.user_id = u.user_id
                    JOIN roles r ON r.role_id = ur.role_id
                    WHERE r.role_name = %s
                    ORDER BY u.user_id
                    """,
                    (role_filter,),
                )
            else:
                cursor.execute("SELECT * FROM users ORDER BY user_id")
            return [_serialize_user(row) for row in cursor.fetchall()]

    def list_roles(self) -> list[dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT role_id, role_name FROM roles ORDER BY role_id")
            return [dict(row) for row in cursor.fetchall()]

    def create_user(
        self,
        full_name: str,
        email: str,
        password_hash: str,
        is_active: bool,
        roles: list[str],
    ) -> dict[str, Any]:
        timestamp = _now_utc_naive()
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    """
                    INSERT INTO users (full_name, email, password_hash, is_active, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (full_name, email, password_hash, 1 if is_active else 0, timestamp, timestamp),
                )
            except IntegrityError:
                conn.rollback()
                raise ValueError("Email already exists")

            user_id = int(cursor.lastrowid)
            assigned_roles: list[str] = []

            for role_name in roles:
                cursor.execute("SELECT role_id FROM roles WHERE role_name = %s", (role_name,))
                role_row = cursor.fetchone()
                if not role_row:
                    continue
                cursor.execute(
                    "INSERT IGNORE INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                    (user_id, role_row["role_id"]),
                )
                assigned_roles.append(role_name)

            conn.commit()

            return {
                "user_id": user_id,
                "full_name": full_name,
                "email": email,
                "password_hash": password_hash,
                "is_active": is_active,
                "created_at": _to_iso_z(timestamp),
                "updated_at": _to_iso_z(timestamp),
                "roles": assigned_roles,
            }

    def list_pantries(self) -> list[dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM pantries ORDER BY pantry_id")
            return [_serialize_pantry(row) for row in cursor.fetchall()]

    def get_pantry_by_id(self, pantry_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM pantries WHERE pantry_id = %s", (pantry_id,))
            row = cursor.fetchone()
            return _serialize_pantry(row) if row else None

    def get_pantry_by_slug(self, slug: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT *
                FROM pantries
                WHERE CAST(pantry_id AS CHAR) = %s
                   OR REPLACE(LOWER(name), ' ', '-') = %s
                LIMIT 1
                """,
                (slug, slug.lower()),
            )
            row = cursor.fetchone()
            return _serialize_pantry(row) if row else None

    def get_pantry_leads(self, pantry_id: int) -> list[dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT u.*
                FROM pantry_leads pl
                JOIN users u ON u.user_id = pl.user_id
                WHERE pl.pantry_id = %s
                ORDER BY u.user_id
                """,
                (pantry_id,),
            )
            return [_serialize_user(row) for row in cursor.fetchall()]

    def is_pantry_lead(self, pantry_id: int, user_id: int) -> bool:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM pantry_leads WHERE pantry_id = %s AND user_id = %s",
                (pantry_id, user_id),
            )
            return cursor.fetchone() is not None

    def create_pantry(self, name: str, location_address: str, lead_ids: list[int]) -> dict[str, Any]:
        timestamp = _now_utc_naive()

        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                INSERT INTO pantries (name, location_address, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                """,
                (name, location_address, timestamp, timestamp),
            )
            pantry_id = int(cursor.lastrowid)

            for lead_id in lead_ids:
                cursor.execute(
                    """
                    SELECT 1
                    FROM user_roles ur
                    JOIN roles r ON r.role_id = ur.role_id
                    WHERE ur.user_id = %s AND r.role_name = 'PANTRY_LEAD'
                    """,
                    (lead_id,),
                )
                if cursor.fetchone() is None:
                    continue
                cursor.execute(
                    "INSERT IGNORE INTO pantry_leads (pantry_id, user_id) VALUES (%s, %s)",
                    (pantry_id, lead_id),
                )

            conn.commit()

        pantry = self.get_pantry_by_id(pantry_id)
        if not pantry:
            raise RuntimeError("Failed to create pantry")
        pantry["leads"] = self.get_pantry_leads(pantry_id)
        return pantry

    def add_pantry_lead(self, pantry_id: int, user_id: int) -> None:
        with get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO pantry_leads (pantry_id, user_id) VALUES (%s, %s)",
                    (pantry_id, user_id),
                )
            except IntegrityError:
                conn.rollback()
                raise ValueError("User already a lead for this pantry")
            conn.commit()

    def remove_pantry_lead(self, pantry_id: int, user_id: int) -> None:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM pantry_leads WHERE pantry_id = %s AND user_id = %s",
                (pantry_id, user_id),
            )
            conn.commit()

    def list_shifts_by_pantry(self, pantry_id: int, include_cancelled: bool = True) -> list[dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            if include_cancelled:
                cursor.execute(
                    "SELECT * FROM shifts WHERE pantry_id = %s ORDER BY shift_id",
                    (pantry_id,),
                )
            else:
                cursor.execute(
                    "SELECT * FROM shifts WHERE pantry_id = %s AND status != 'CANCELLED' ORDER BY shift_id",
                    (pantry_id,),
                )
            return [_serialize_shift(row) for row in cursor.fetchall()]

    def get_shift_by_id(self, shift_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM shifts WHERE shift_id = %s", (shift_id,))
            row = cursor.fetchone()
            return _serialize_shift(row) if row else None

    def create_shift(
        self,
        pantry_id: int,
        shift_name: str,
        start_time: str,
        end_time: str,
        status: str,
        created_by: int,
    ) -> dict[str, Any]:
        timestamp = _now_utc_naive()
        start_dt = _parse_iso_to_dt(start_time)
        end_dt = _parse_iso_to_dt(end_time)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO shifts (
                    pantry_id,
                    shift_name,
                    start_time,
                    end_time,
                    status,
                    created_by,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (pantry_id, shift_name, start_dt, end_dt, status, created_by, timestamp, timestamp),
            )
            shift_id = int(cursor.lastrowid)
            conn.commit()

        shift = self.get_shift_by_id(shift_id)
        if not shift:
            raise RuntimeError("Failed to create shift")
        return shift

    def update_shift(self, shift_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get_shift_by_id(shift_id)
        if not existing:
            return None

        updates: list[str] = []
        values: list[Any] = []
        if "shift_name" in payload:
            updates.append("shift_name = %s")
            values.append(payload["shift_name"])
        if "start_time" in payload:
            updates.append("start_time = %s")
            values.append(_parse_iso_to_dt(payload["start_time"]))
        if "end_time" in payload:
            updates.append("end_time = %s")
            values.append(_parse_iso_to_dt(payload["end_time"]))
        if "status" in payload:
            updates.append("status = %s")
            values.append(payload["status"])

        if updates:
            updates.append("updated_at = %s")
            values.append(_now_utc_naive())
            values.append(shift_id)
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE shifts SET {', '.join(updates)} WHERE shift_id = %s",
                    tuple(values),
                )
                conn.commit()

        return self.get_shift_by_id(shift_id)

    def delete_shift(self, shift_id: int) -> None:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM shifts WHERE shift_id = %s", (shift_id,))
            conn.commit()

    def list_shift_roles(self, shift_id: int) -> list[dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM shift_roles WHERE shift_id = %s ORDER BY shift_role_id",
                (shift_id,),
            )
            return [_serialize_shift_role(row) for row in cursor.fetchall()]

    def get_shift_role_by_id(self, shift_role_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM shift_roles WHERE shift_role_id = %s", (shift_role_id,))
            row = cursor.fetchone()
            return _serialize_shift_role(row) if row else None

    def create_shift_role(self, shift_id: int, role_title: str, required_count: int) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO shift_roles (shift_id, role_title, required_count, filled_count, status)
                VALUES (%s, %s, %s, 0, 'OPEN')
                """,
                (shift_id, role_title, required_count),
            )
            shift_role_id = int(cursor.lastrowid)
            conn.commit()

        role = self.get_shift_role_by_id(shift_role_id)
        if not role:
            raise RuntimeError("Failed to create shift role")
        return role

    def update_shift_role(self, shift_role_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get_shift_role_by_id(shift_role_id)
        if not existing:
            return None

        updates: list[str] = []
        values: list[Any] = []
        if "role_title" in payload:
            updates.append("role_title = %s")
            values.append(payload["role_title"])
        if "required_count" in payload:
            updates.append("required_count = %s")
            values.append(int(payload["required_count"]))
        if "status" in payload:
            updates.append("status = %s")
            values.append(payload["status"])
        if "filled_count" in payload:
            updates.append("filled_count = %s")
            values.append(int(payload["filled_count"]))

        if updates:
            values.append(shift_role_id)
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE shift_roles SET {', '.join(updates)} WHERE shift_role_id = %s",
                    tuple(values),
                )
                conn.commit()

        return self.get_shift_role_by_id(shift_role_id)

    def delete_shift_role(self, shift_role_id: int) -> None:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM shift_roles WHERE shift_role_id = %s", (shift_role_id,))
            conn.commit()

    def list_shift_signups(self, shift_role_id: int) -> list[dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM shift_signups WHERE shift_role_id = %s ORDER BY signup_id",
                (shift_role_id,),
            )
            return [_serialize_signup(row) for row in cursor.fetchall()]

    def list_signups_by_user(self, user_id: int) -> list[dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT
                    ss.signup_id,
                    ss.user_id,
                    ss.signup_status,
                    ss.created_at,
                    sr.shift_role_id,
                    sr.role_title,
                    sr.required_count,
                    sr.filled_count,
                    sr.status AS role_status,
                    s.shift_id,
                    s.shift_name,
                    s.start_time,
                    s.end_time,
                    s.status AS shift_status,
                    p.pantry_id,
                    p.name AS pantry_name,
                    p.location_address AS pantry_location
                FROM shift_signups ss
                JOIN shift_roles sr ON sr.shift_role_id = ss.shift_role_id
                JOIN shifts s ON s.shift_id = sr.shift_id
                JOIN pantries p ON p.pantry_id = s.pantry_id
                WHERE ss.user_id = %s
                ORDER BY s.start_time ASC, ss.signup_id ASC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()

        return [
            {
                "signup_id": int(row["signup_id"]),
                "user_id": int(row["user_id"]),
                "signup_status": row["signup_status"],
                "created_at": _to_iso_z(row["created_at"]),
                "shift_role_id": int(row["shift_role_id"]),
                "role_title": row["role_title"],
                "required_count": int(row["required_count"]),
                "filled_count": int(row["filled_count"]),
                "role_status": row["role_status"],
                "shift_id": int(row["shift_id"]),
                "shift_name": row["shift_name"],
                "start_time": _to_iso_z(row["start_time"]),
                "end_time": _to_iso_z(row["end_time"]),
                "shift_status": row["shift_status"],
                "pantry_id": int(row["pantry_id"]),
                "pantry_name": row["pantry_name"],
                "pantry_location": row["pantry_location"],
            }
            for row in rows
        ]

    def get_signup_by_id(self, signup_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM shift_signups WHERE signup_id = %s", (signup_id,))
            row = cursor.fetchone()
            return _serialize_signup(row) if row else None

    def create_signup(self, shift_role_id: int, user_id: int, signup_status: str) -> dict[str, Any]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            now = _now_utc_naive()

            cursor.execute(
                "SELECT * FROM shift_roles WHERE shift_role_id = %s FOR UPDATE",
                (shift_role_id,),
            )
            role_row = cursor.fetchone()
            if not role_row:
                conn.rollback()
                raise LookupError("Shift role not found")
            if str(role_row["status"]).upper() == "CANCELLED":
                conn.rollback()
                raise RuntimeError("This role is unavailable")

            cursor.execute(
                "SELECT status FROM shifts WHERE shift_id = %s",
                (int(role_row["shift_id"]),),
            )
            shift_row = cursor.fetchone()
            if not shift_row:
                conn.rollback()
                raise LookupError("Shift not found")
            if str(shift_row["status"]).upper() == "CANCELLED":
                conn.rollback()
                raise RuntimeError("This shift is cancelled")

            cursor.execute(
                "SELECT 1 FROM shift_signups WHERE shift_role_id = %s AND user_id = %s",
                (shift_role_id, user_id),
            )
            if cursor.fetchone() is not None:
                conn.rollback()
                raise ValueError("Already signed up")

            cursor.execute(
                """
                SELECT COUNT(*) AS active_count
                FROM shift_signups
                WHERE shift_role_id = %s
                  AND UPPER(signup_status) IN ('CONFIRMED', 'SHOW_UP', 'NO_SHOW')
                """,
                (shift_role_id,),
            )
            filled_count = int(cursor.fetchone()["active_count"])
            required_count = int(role_row["required_count"])
            if filled_count >= required_count:
                conn.rollback()
                raise RuntimeError("This role is full")

            try:
                cursor.execute(
                    """
                    INSERT INTO shift_signups (shift_role_id, user_id, signup_status, created_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (shift_role_id, user_id, signup_status, now),
                )
            except IntegrityError:
                conn.rollback()
                raise ValueError("Already signed up")

            self._recalculate_role_capacity(cursor, shift_role_id)
            signup_id = int(cursor.lastrowid)
            conn.commit()

        signup = self.get_signup_by_id(signup_id)
        if not signup:
            raise RuntimeError("Failed to create signup")
        return signup

    def delete_signup(self, signup_id: int) -> None:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM shift_signups WHERE signup_id = %s FOR UPDATE", (signup_id,))
            signup = cursor.fetchone()
            if not signup:
                conn.rollback()
                return

            shift_role_id = int(signup["shift_role_id"])
            cursor.execute(
                "SELECT * FROM shift_roles WHERE shift_role_id = %s FOR UPDATE",
                (shift_role_id,),
            )
            role_row = cursor.fetchone()

            cursor.execute("DELETE FROM shift_signups WHERE signup_id = %s", (signup_id,))
            if role_row:
                self._recalculate_role_capacity(cursor, shift_role_id)

            conn.commit()

    def update_signup(self, signup_id: int, signup_status: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM shift_signups WHERE signup_id = %s FOR UPDATE", (signup_id,))
            signup_row = cursor.fetchone()
            if not signup_row:
                conn.rollback()
                return None

            shift_role_id = int(signup_row["shift_role_id"])
            cursor.execute("SELECT * FROM shift_roles WHERE shift_role_id = %s FOR UPDATE", (shift_role_id,))
            role_row = cursor.fetchone()
            if not role_row:
                conn.rollback()
                return None

            cursor.execute(
                "UPDATE shift_signups SET signup_status = %s WHERE signup_id = %s",
                (signup_status, signup_id),
            )
            self._recalculate_role_capacity(cursor, shift_role_id)
            conn.commit()
        return self.get_signup_by_id(signup_id)

    def is_empty(self) -> bool:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            users_count = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM roles")
            roles_count = int(cursor.fetchone()[0])
            return users_count == 0 and roles_count == 0
