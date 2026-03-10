from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from db.mysql import get_connection


TABLES_INSERT_ORDER = [
    "roles",
    "users",
    "user_roles",
    "pantries",
    "pantry_leads",
    "shifts",
    "shift_roles",
    "shift_signups",
]

TABLES_TRUNCATE_ORDER = [
    "shift_signups",
    "shift_roles",
    "shifts",
    "pantry_leads",
    "pantries",
    "user_roles",
    "users",
    "roles",
]


def parse_iso_to_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def recalculate_all_attendance_scores(cursor: Any) -> None:
    cursor.execute(
        """
        UPDATE users u
        LEFT JOIN (
            SELECT
                user_id,
                SUM(CASE WHEN UPPER(signup_status) = 'SHOW_UP' THEN 1 ELSE 0 END) AS attended_count,
                SUM(CASE WHEN UPPER(signup_status) IN ('SHOW_UP', 'NO_SHOW') THEN 1 ELSE 0 END) AS marked_count
            FROM shift_signups
            GROUP BY user_id
        ) stats ON stats.user_id = u.user_id
        SET u.attendance_score = CASE
            WHEN COALESCE(stats.marked_count, 0) = 0 THEN 100
            ELSE ROUND((COALESCE(stats.attended_count, 0) * 100.0) / stats.marked_count)
        END
        """
    )


def seed_mysql_from_json(data_path: Path, truncate: bool = False) -> None:
    payload = json.loads(data_path.read_text(encoding="utf-8"))

    with get_connection() as conn:
        cursor = conn.cursor()

        if truncate:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            for table in TABLES_TRUNCATE_ORDER:
                cursor.execute(f"TRUNCATE TABLE {table}")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        for role in payload.get("roles", []):
            cursor.execute(
                """
                INSERT INTO roles (role_id, role_name)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE role_name = VALUES(role_name)
                """,
                (role["role_id"], role["role_name"]),
            )

        for user in payload.get("users", []):
            cursor.execute(
                """
                INSERT INTO users (
                    user_id,
                    full_name,
                    email,
                    password_hash,
                    is_active,
                    attendance_score,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    full_name = VALUES(full_name),
                    email = VALUES(email),
                    password_hash = VALUES(password_hash),
                    is_active = VALUES(is_active),
                    attendance_score = VALUES(attendance_score),
                    updated_at = VALUES(updated_at)
                """,
                (
                    user["user_id"],
                    user["full_name"],
                    user["email"],
                    user["password_hash"],
                    1 if user.get("is_active", True) else 0,
                    int(user.get("attendance_score", 100)),
                    parse_iso_to_dt(user.get("created_at")),
                    parse_iso_to_dt(user.get("updated_at") or user.get("created_at")),
                ),
            )

        for user_role in payload.get("user_roles", []):
            cursor.execute(
                """
                INSERT INTO user_roles (user_id, role_id)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE role_id = VALUES(role_id)
                """,
                (user_role["user_id"], user_role["role_id"]),
            )

        for pantry in payload.get("pantries", []):
            cursor.execute(
                """
                INSERT INTO pantries (pantry_id, name, location_address, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    location_address = VALUES(location_address),
                    updated_at = VALUES(updated_at)
                """,
                (
                    pantry["pantry_id"],
                    pantry["name"],
                    pantry["location_address"],
                    parse_iso_to_dt(pantry.get("created_at")),
                    parse_iso_to_dt(pantry.get("updated_at") or pantry.get("created_at")),
                ),
            )

        for pantry_lead in payload.get("pantry_leads", []):
            cursor.execute(
                """
                INSERT INTO pantry_leads (pantry_id, user_id)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE user_id = VALUES(user_id)
                """,
                (pantry_lead["pantry_id"], pantry_lead["user_id"]),
            )

        for shift in payload.get("shifts", []):
            cursor.execute(
                """
                INSERT INTO shifts (
                    shift_id,
                    pantry_id,
                    shift_name,
                    start_time,
                    end_time,
                    status,
                    created_by,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    pantry_id = VALUES(pantry_id),
                    shift_name = VALUES(shift_name),
                    start_time = VALUES(start_time),
                    end_time = VALUES(end_time),
                    status = VALUES(status),
                    created_by = VALUES(created_by),
                    updated_at = VALUES(updated_at)
                """,
                (
                    shift["shift_id"],
                    shift["pantry_id"],
                    shift["shift_name"],
                    parse_iso_to_dt(shift["start_time"]),
                    parse_iso_to_dt(shift["end_time"]),
                    shift.get("status", "OPEN"),
                    shift["created_by"],
                    parse_iso_to_dt(shift.get("created_at")),
                    parse_iso_to_dt(shift.get("updated_at") or shift.get("created_at")),
                ),
            )

        for shift_role in payload.get("shift_roles", []):
            cursor.execute(
                """
                INSERT INTO shift_roles (
                    shift_role_id,
                    shift_id,
                    role_title,
                    required_count,
                    filled_count,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    shift_id = VALUES(shift_id),
                    role_title = VALUES(role_title),
                    required_count = VALUES(required_count),
                    filled_count = VALUES(filled_count),
                    status = VALUES(status)
                """,
                (
                    shift_role["shift_role_id"],
                    shift_role["shift_id"],
                    shift_role["role_title"],
                    shift_role["required_count"],
                    shift_role.get("filled_count", 0),
                    shift_role.get("status", "OPEN"),
                ),
            )

        for signup in payload.get("shift_signups", []):
            cursor.execute(
                """
                INSERT INTO shift_signups (
                    signup_id,
                    shift_role_id,
                    user_id,
                    signup_status,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    shift_role_id = VALUES(shift_role_id),
                    user_id = VALUES(user_id),
                    signup_status = VALUES(signup_status),
                    created_at = VALUES(created_at)
                """,
                (
                    signup["signup_id"],
                    signup["shift_role_id"],
                    signup["user_id"],
                    signup.get("signup_status", "CONFIRMED"),
                    parse_iso_to_dt(signup.get("created_at")),
                ),
            )

        recalculate_all_attendance_scores(cursor)

        for table, key in [
            ("users", "user_id"),
            ("roles", "role_id"),
            ("pantries", "pantry_id"),
            ("shifts", "shift_id"),
            ("shift_roles", "shift_role_id"),
            ("shift_signups", "signup_id"),
        ]:
            rows: list[dict[str, Any]] = payload.get(table, [])
            max_id = max((int(row.get(key, 0)) for row in rows), default=0)
            cursor.execute(f"ALTER TABLE {table} AUTO_INCREMENT = %s", (max_id + 1,))

        conn.commit()


def should_seed_mysql() -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        users_count = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM roles")
        roles_count = int(cursor.fetchone()[0])
        return users_count == 0 and roles_count == 0
