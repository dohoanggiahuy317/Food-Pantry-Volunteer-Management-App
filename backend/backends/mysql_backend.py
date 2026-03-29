from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from mysql.connector import IntegrityError

from backends.base import StoreBackend
from db.mysql import get_connection

ACTIVE_SIGNUP_STATUSES = ("CONFIRMED", "SHOW_UP", "NO_SHOW")
PENDING_SIGNUP_STATUS = "PENDING_CONFIRMATION"
RESERVATION_WINDOW_HOURS = 48


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
        "phone_number": row.get("phone_number"),
        "auth_provider": row.get("auth_provider"),
        "auth_uid": row.get("auth_uid"),
        "attendance_score": int(row.get("attendance_score", 100)),
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
    reservation_expires_at = row.get("reservation_expires_at")
    return {
        "signup_id": row["signup_id"],
        "shift_role_id": row["shift_role_id"],
        "user_id": row["user_id"],
        "signup_status": row["signup_status"],
        "reservation_expires_at": _to_iso_z(reservation_expires_at) if reservation_expires_at else None,
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
              AND (
                    UPPER(signup_status) IN ('CONFIRMED', 'SHOW_UP', 'NO_SHOW')
                    OR (
                        UPPER(signup_status) = 'PENDING_CONFIRMATION'
                        AND reservation_expires_at IS NOT NULL
                        AND reservation_expires_at > UTC_TIMESTAMP(6)
                    )
              )
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

    def _recalculate_user_attendance_score(self, cursor: Any, user_id: int) -> None:
        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN UPPER(signup_status) = 'SHOW_UP' THEN 1 ELSE 0 END) AS attended_count,
                SUM(CASE WHEN UPPER(signup_status) IN ('SHOW_UP', 'NO_SHOW') THEN 1 ELSE 0 END) AS marked_count
            FROM shift_signups
            WHERE user_id = %s
            """,
            (user_id,),
        )
        score_row = cursor.fetchone() or {}
        attended_count = int(score_row.get("attended_count") or 0)
        marked_count = int(score_row.get("marked_count") or 0)
        if marked_count == 0:
            attendance_score = 100
        else:
            attendance_score = round((attended_count * 100) / marked_count)

        cursor.execute(
            "UPDATE users SET attendance_score = %s WHERE user_id = %s",
            (attendance_score, user_id),
        )

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            return _serialize_user(row) if row else None

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        normalized_email = str(email).strip().lower()
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE LOWER(email) = %s LIMIT 1", (normalized_email,))
            row = cursor.fetchone()
            return _serialize_user(row) if row else None

    def get_user_by_auth_uid(self, auth_uid: str) -> dict[str, Any] | None:
        normalized_auth_uid = str(auth_uid).strip()
        if not normalized_auth_uid:
            return None
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE auth_uid = %s LIMIT 1", (normalized_auth_uid,))
            row = cursor.fetchone()
            return _serialize_user(row) if row else None

    def get_role_by_id(self, role_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT role_id, role_name FROM roles WHERE role_id = %s LIMIT 1", (role_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

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
        phone_number: str | None,
        roles: list[str],
        auth_provider: str | None = None,
        auth_uid: str | None = None,
    ) -> dict[str, Any]:
        normalized_email = str(email).strip().lower()
        normalized_auth_provider = str(auth_provider).strip() if auth_provider is not None else ""
        normalized_auth_uid = str(auth_uid).strip() if auth_uid is not None else ""
        normalized_auth_provider = normalized_auth_provider or None
        normalized_auth_uid = normalized_auth_uid or None
        timestamp = _now_utc_naive()
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    """
                    INSERT INTO users (
                        full_name,
                        email,
                        phone_number,
                        auth_provider,
                        auth_uid,
                        attendance_score,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        full_name,
                        normalized_email,
                        phone_number,
                        normalized_auth_provider,
                        normalized_auth_uid,
                        100,
                        timestamp,
                        timestamp,
                    ),
                )
            except IntegrityError:
                conn.rollback()
                if normalized_auth_uid and self.get_user_by_auth_uid(normalized_auth_uid):
                    raise ValueError("Authentication identity already exists")
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
                "email": normalized_email,
                "phone_number": phone_number,
                "auth_provider": normalized_auth_provider,
                "auth_uid": normalized_auth_uid,
                "attendance_score": 100,
                "created_at": _to_iso_z(timestamp),
                "updated_at": _to_iso_z(timestamp),
                "roles": assigned_roles,
            }

    def update_user(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get_user_by_id(user_id)
        if not existing:
            return None

        updates: list[str] = []
        values: list[Any] = []

        if "full_name" in payload:
            updates.append("full_name = %s")
            values.append(payload["full_name"])
        if "email" in payload:
            updates.append("email = %s")
            values.append(str(payload["email"]).strip().lower())
        if "phone_number" in payload:
            updates.append("phone_number = %s")
            values.append(payload["phone_number"])
        if "auth_provider" in payload:
            updates.append("auth_provider = %s")
            normalized_auth_provider = str(payload["auth_provider"]).strip() if payload["auth_provider"] is not None else ""
            values.append(normalized_auth_provider or None)
        if "auth_uid" in payload:
            updates.append("auth_uid = %s")
            normalized_auth_uid = str(payload["auth_uid"]).strip() if payload["auth_uid"] is not None else ""
            values.append(normalized_auth_uid or None)

        if not updates:
            return existing

        updates.append("updated_at = %s")
        values.append(_now_utc_naive())
        values.append(user_id)

        with get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE user_id = %s",
                    tuple(values),
                )
            except IntegrityError:
                conn.rollback()
                attempted_auth_uid = str(payload.get("auth_uid", "")).strip() or None
                if attempted_auth_uid and self.get_user_by_auth_uid(attempted_auth_uid):
                    raise ValueError("Authentication identity already exists")
                raise ValueError("Email already exists")
            conn.commit()

        return self.get_user_by_id(user_id)

    def replace_user_roles(self, user_id: int, role_ids: list[int]) -> list[str] | None:
        if not self.get_user_by_id(user_id):
            return None

        normalized_role_ids: list[int] = []
        seen_role_ids: set[int] = set()
        for role_id in role_ids:
            normalized_role_id = int(role_id)
            if normalized_role_id in seen_role_ids:
                continue
            seen_role_ids.add(normalized_role_id)
            normalized_role_ids.append(normalized_role_id)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
            for role_id in normalized_role_ids:
                cursor.execute(
                    "INSERT IGNORE INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                    (user_id, role_id),
                )
            cursor.execute("UPDATE users SET updated_at = %s WHERE user_id = %s", (_now_utc_naive(), user_id))
            conn.commit()

        return self.get_user_roles(user_id)

    def delete_user(self, user_id: int) -> None:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            conn.commit()

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

    def update_pantry(self, pantry_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {k: v for k, v in payload.items() if k in {"name", "location_address"}}
        if not allowed:
            return self.get_pantry_by_id(pantry_id)
        allowed["updated_at"] = _now_utc_naive()
        set_clause = ", ".join(f"{k} = %s" for k in allowed)
        values = list(allowed.values()) + [pantry_id]
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE pantries SET {set_clause} WHERE pantry_id = %s", values)
            conn.commit()
        return self.get_pantry_by_id(pantry_id)

    def delete_pantry(self, pantry_id: int) -> None:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pantries WHERE pantry_id = %s", (pantry_id,))
            conn.commit()

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
    
    def list_non_expired_shifts_by_pantry(
        self,
        pantry_id: int,
        include_cancelled: bool = True,
    ) -> list[dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM shifts WHERE pantry_id = %s AND end_time >= UTC_TIMESTAMP()"
            if not include_cancelled:
                query += " AND status != 'CANCELLED'"
            query += " ORDER BY shift_id"
            cursor.execute(query, (pantry_id,))
            return [_serialize_shift(row) for row in cursor.fetchall()]

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
                    ss.reservation_expires_at,
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
                "reservation_expires_at": _to_iso_z(row["reservation_expires_at"]) if row["reservation_expires_at"] else None,
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
            existing = cursor.fetchone()
            if existing is not None:
                conn.rollback()
                raise ValueError("Already signed up")

            cursor.execute(
                """
                SELECT COUNT(*) AS active_count
                FROM shift_signups
                WHERE shift_role_id = %s
                  AND (
                        UPPER(signup_status) IN ('CONFIRMED', 'SHOW_UP', 'NO_SHOW')
                        OR (
                            UPPER(signup_status) = 'PENDING_CONFIRMATION'
                            AND reservation_expires_at IS NOT NULL
                            AND reservation_expires_at > %s
                        )
                  )
                """,
                (shift_role_id, now),
            )
            filled_count = int(cursor.fetchone()["active_count"])
            required_count = int(role_row["required_count"])
            if filled_count >= required_count:
                conn.rollback()
                raise RuntimeError("This role is full")

            try:
                cursor.execute(
                    """
                    INSERT INTO shift_signups (
                        shift_role_id,
                        user_id,
                        signup_status,
                        reservation_expires_at,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        shift_role_id,
                        user_id,
                        signup_status,
                        now + timedelta(hours=RESERVATION_WINDOW_HOURS)
                        if str(signup_status).upper() == PENDING_SIGNUP_STATUS
                        else None,
                        now,
                    ),
                )
            except IntegrityError:
                conn.rollback()
                raise ValueError("Already signed up")

            signup_id = int(cursor.lastrowid)
            self._recalculate_role_capacity(cursor, shift_role_id)
            self._recalculate_user_attendance_score(cursor, user_id)
            conn.commit()

        return {
            "signup_id": signup_id,
            "shift_role_id": shift_role_id,
            "user_id": user_id,
            "signup_status": signup_status,
            "created_at": _to_iso_z(now),
        }

    def delete_signup(self, signup_id: int) -> None:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM shift_signups WHERE signup_id = %s FOR UPDATE", (signup_id,))
            signup = cursor.fetchone()
            if not signup:
                conn.rollback()
                return

            shift_role_id = int(signup["shift_role_id"])
            user_id = int(signup["user_id"])
            cursor.execute(
                "SELECT * FROM shift_roles WHERE shift_role_id = %s FOR UPDATE",
                (shift_role_id,),
            )
            role_row = cursor.fetchone()

            cursor.execute("DELETE FROM shift_signups WHERE signup_id = %s", (signup_id,))
            if role_row:
                self._recalculate_role_capacity(cursor, shift_role_id)
            self._recalculate_user_attendance_score(cursor, user_id)

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
            user_id = int(signup_row["user_id"])
            cursor.execute("SELECT * FROM shift_roles WHERE shift_role_id = %s FOR UPDATE", (shift_role_id,))
            role_row = cursor.fetchone()
            if not role_row:
                conn.rollback()
                return None

            cursor.execute(
                "UPDATE shift_signups SET signup_status = %s, reservation_expires_at = %s WHERE signup_id = %s",
                (
                    signup_status,
                    _now_utc_naive() + timedelta(hours=RESERVATION_WINDOW_HOURS)
                    if str(signup_status).upper() == PENDING_SIGNUP_STATUS
                    else None,
                    signup_id,
                ),
            )
            self._recalculate_role_capacity(cursor, shift_role_id)
            self._recalculate_user_attendance_score(cursor, user_id)
            conn.commit()
        return self.get_signup_by_id(signup_id)

    def bulk_mark_shift_signups_pending(self, shift_id: int, reservation_expires_at: str) -> list[dict[str, Any]]:
        reservation_expires_dt = _parse_iso_to_dt(reservation_expires_at)
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT ss.signup_id, ss.user_id
                FROM shift_signups ss
                JOIN shift_roles sr ON sr.shift_role_id = ss.shift_role_id
                WHERE sr.shift_id = %s
                  AND UPPER(ss.signup_status) NOT IN ('CANCELLED', 'WAITLISTED')
                FOR UPDATE
                """,
                (shift_id,),
            )
            affected_rows = cursor.fetchall()
            if not affected_rows:
                conn.commit()
                return []

            cursor.execute(
                """
                UPDATE shift_signups ss
                JOIN shift_roles sr ON sr.shift_role_id = ss.shift_role_id
                SET ss.signup_status = 'PENDING_CONFIRMATION',
                    ss.reservation_expires_at = %s
                WHERE sr.shift_id = %s
                  AND UPPER(ss.signup_status) NOT IN ('CANCELLED', 'WAITLISTED')
                """,
                (reservation_expires_dt, shift_id),
            )

            cursor.execute("SELECT shift_role_id FROM shift_roles WHERE shift_id = %s", (shift_id,))
            role_ids = [int(row["shift_role_id"]) for row in cursor.fetchall()]
            for role_id in role_ids:
                self._recalculate_role_capacity(cursor, role_id)

            conn.commit()
            return [
                {
                    "signup_id": int(row["signup_id"]),
                    "user_id": int(row["user_id"]),
                }
                for row in affected_rows
            ]

    def expire_pending_signups(self, shift_id: int, now_utc: str) -> int:
        now_dt = _parse_iso_to_dt(now_utc)
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT ss.signup_id, ss.shift_role_id
                FROM shift_signups ss
                JOIN shift_roles sr ON sr.shift_role_id = ss.shift_role_id
                JOIN shifts s ON s.shift_id = sr.shift_id
                WHERE sr.shift_id = %s
                  AND UPPER(ss.signup_status) = 'PENDING_CONFIRMATION'
                  AND (
                        s.start_time <= %s
                        OR (
                            ss.reservation_expires_at IS NOT NULL
                            AND ss.reservation_expires_at <= %s
                        )
                  )
                FOR UPDATE
                """,
                (shift_id, now_dt, now_dt),
            )
            rows = cursor.fetchall()
            if not rows:
                conn.commit()
                return 0

            cursor.execute(
                """
                UPDATE shift_signups ss
                JOIN shift_roles sr ON sr.shift_role_id = ss.shift_role_id
                JOIN shifts s ON s.shift_id = sr.shift_id
                SET ss.signup_status = 'CANCELLED',
                    ss.reservation_expires_at = NULL
                WHERE sr.shift_id = %s
                  AND UPPER(ss.signup_status) = 'PENDING_CONFIRMATION'
                  AND (
                        s.start_time <= %s
                        OR (
                            ss.reservation_expires_at IS NOT NULL
                            AND ss.reservation_expires_at <= %s
                        )
                  )
                """,
                (shift_id, now_dt, now_dt),
            )

            role_ids = {int(row["shift_role_id"]) for row in rows}
            for role_id in role_ids:
                self._recalculate_role_capacity(cursor, role_id)

            conn.commit()
            return len(rows)

    def reconfirm_pending_signup(self, signup_id: int, now_utc: str) -> dict[str, Any]:
        now_dt = _parse_iso_to_dt(now_utc)
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM shift_signups WHERE signup_id = %s FOR UPDATE", (signup_id,))
            signup_row = cursor.fetchone()
            if not signup_row:
                conn.rollback()
                return {"result": "NOT_FOUND", "signup": None}

            shift_role_id = int(signup_row["shift_role_id"])
            current_status = str(signup_row["signup_status"]).upper()
            if current_status != PENDING_SIGNUP_STATUS:
                conn.rollback()
                return {"result": "NOT_PENDING", "signup": _serialize_signup(signup_row)}

            cursor.execute("SELECT * FROM shift_roles WHERE shift_role_id = %s FOR UPDATE", (shift_role_id,))
            role_row = cursor.fetchone()
            if not role_row:
                conn.rollback()
                return {"result": "NOT_FOUND", "signup": None}

            cursor.execute("SELECT * FROM shifts WHERE shift_id = %s FOR UPDATE", (int(role_row["shift_id"]),))
            shift_row = cursor.fetchone()
            if not shift_row:
                conn.rollback()
                return {"result": "NOT_FOUND", "signup": None}

            reservation_expires_at = signup_row.get("reservation_expires_at")
            if shift_row["start_time"] <= now_dt or (
                reservation_expires_at is not None and reservation_expires_at <= now_dt
            ):
                cursor.execute(
                    """
                    UPDATE shift_signups
                    SET signup_status = 'CANCELLED',
                        reservation_expires_at = NULL
                    WHERE signup_id = %s
                    """,
                    (signup_id,),
                )
                self._recalculate_role_capacity(cursor, shift_role_id)
                self._recalculate_user_attendance_score(cursor, int(signup_row["user_id"]))
                conn.commit()
                updated = self.get_signup_by_id(signup_id)
                return {"result": "EXPIRED", "signup": updated}

            if str(shift_row["status"]).upper() == "CANCELLED" or str(role_row["status"]).upper() == "CANCELLED":
                cursor.execute(
                    """
                    UPDATE shift_signups
                    SET signup_status = 'WAITLISTED',
                        reservation_expires_at = NULL
                    WHERE signup_id = %s
                    """,
                    (signup_id,),
                )
                self._recalculate_role_capacity(cursor, shift_role_id)
                self._recalculate_user_attendance_score(cursor, int(signup_row["user_id"]))
                conn.commit()
                updated = self.get_signup_by_id(signup_id)
                return {"result": "WAITLISTED", "signup": updated}

            cursor.execute(
                """
                SELECT COUNT(*) AS confirmed_count
                FROM shift_signups
                WHERE shift_role_id = %s
                  AND UPPER(signup_status) IN ('CONFIRMED', 'SHOW_UP', 'NO_SHOW')
                """,
                (shift_role_id,),
            )
            confirmed_count = int(cursor.fetchone()["confirmed_count"])
            required_count = int(role_row["required_count"])
            if confirmed_count >= required_count:
                cursor.execute(
                    """
                    UPDATE shift_signups
                    SET signup_status = 'WAITLISTED',
                        reservation_expires_at = NULL
                    WHERE signup_id = %s
                    """,
                    (signup_id,),
                )
                self._recalculate_role_capacity(cursor, shift_role_id)
                self._recalculate_user_attendance_score(cursor, int(signup_row["user_id"]))
                conn.commit()
                updated = self.get_signup_by_id(signup_id)
                return {"result": "WAITLISTED", "signup": updated}

            cursor.execute(
                """
                UPDATE shift_signups
                SET signup_status = 'CONFIRMED',
                    reservation_expires_at = NULL
                WHERE signup_id = %s
                """,
                (signup_id,),
            )
            self._recalculate_role_capacity(cursor, shift_role_id)
            self._recalculate_user_attendance_score(cursor, int(signup_row["user_id"]))
            conn.commit()
            updated = self.get_signup_by_id(signup_id)
            return {"result": "CONFIRMED", "signup": updated}

    def is_empty(self) -> bool:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            users_count = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM roles")
            roles_count = int(cursor.fetchone()[0])
            return users_count == 0 and roles_count == 0
