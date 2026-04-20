from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

STATE_TABLE_NAME = "app_bootstrap_state"
STATE_KEY_SCHEMA_SIGNATURE = "demo_schema_signature"
DEFAULT_BOOTSTRAP_MODE = "disabled"
BOOTSTRAP_MODE_RESET_IF_CHANGED = "reset_if_untracked_or_schema_changed"
SEED_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "mysql.json"
APP_TABLES = [
    "shift_signups",
    "shift_roles",
    "shifts",
    "shift_series",
    "pantry_subscriptions",
    "pantry_leads",
    "pantries",
    "user_roles",
    "users",
    "roles",
]


@dataclass(frozen=True)
class BootstrapDecision:
    should_reset: bool
    reason: str
    schema_signature: str
    previous_signature: str | None


def migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def compute_schema_signature() -> str:
    digest = hashlib.sha256()
    migration_files = sorted(migrations_dir().glob("*.sql"))
    for migration_file in migration_files:
        digest.update(migration_file.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(migration_file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def ensure_state_table() -> None:
    from db.mysql import get_connection

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {STATE_TABLE_NAME} (
              state_key VARCHAR(128) PRIMARY KEY,
              state_value TEXT NOT NULL,
              updated_at DATETIME(6) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.commit()


def get_state_value(state_key: str) -> str | None:
    from db.mysql import get_connection

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT state_value FROM {STATE_TABLE_NAME} WHERE state_key = %s", (state_key,))
        row = cursor.fetchone()
        return str(row[0]) if row else None


def set_state_value(state_key: str, state_value: str) -> None:
    from db.mysql import get_connection

    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            INSERT INTO {STATE_TABLE_NAME} (state_key, state_value, updated_at)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
              state_value = VALUES(state_value),
              updated_at = VALUES(updated_at)
            """,
            (state_key, state_value, timestamp),
        )
        conn.commit()


def determine_bootstrap_decision(mode: str, schema_signature: str, previous_signature: str | None) -> BootstrapDecision:
    normalized_mode = str(mode or DEFAULT_BOOTSTRAP_MODE).strip().lower()
    if normalized_mode == DEFAULT_BOOTSTRAP_MODE:
        return BootstrapDecision(
            should_reset=False,
            reason="bootstrap_disabled",
            schema_signature=schema_signature,
            previous_signature=previous_signature,
        )
    if normalized_mode != BOOTSTRAP_MODE_RESET_IF_CHANGED:
        raise ValueError(f"Unsupported DEMO_DB_BOOTSTRAP_MODE: {mode}")
    if not previous_signature:
        return BootstrapDecision(
            should_reset=True,
            reason="bootstrap_untracked_database",
            schema_signature=schema_signature,
            previous_signature=None,
        )
    if previous_signature == schema_signature:
        return BootstrapDecision(
            should_reset=False,
            reason="bootstrap_schema_unchanged",
            schema_signature=schema_signature,
            previous_signature=previous_signature,
        )
    return BootstrapDecision(
        should_reset=True,
        reason="bootstrap_schema_changed",
        schema_signature=schema_signature,
        previous_signature=previous_signature,
    )


def drop_app_tables() -> None:
    from db.mysql import get_connection

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table_name in APP_TABLES:
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()


def run_demo_bootstrap(mode: str | None = None) -> BootstrapDecision:
    from db.init_schema import init_schema
    from db.seed import seed_mysql_from_json

    normalized_mode = str(mode or os.getenv("DEMO_DB_BOOTSTRAP_MODE", DEFAULT_BOOTSTRAP_MODE)).strip().lower()
    schema_signature = compute_schema_signature()
    if normalized_mode == DEFAULT_BOOTSTRAP_MODE:
        return determine_bootstrap_decision(normalized_mode, schema_signature, None)

    ensure_state_table()
    previous_signature = get_state_value(STATE_KEY_SCHEMA_SIGNATURE)
    decision = determine_bootstrap_decision(normalized_mode, schema_signature, previous_signature)
    if not decision.should_reset:
        print(
            f"Demo bootstrap skipped: {decision.reason} "
            f"(schema_signature={decision.schema_signature}, previous_signature={decision.previous_signature})"
        )
        return decision

    print(
        f"Demo bootstrap resetting database: {decision.reason} "
        f"(schema_signature={decision.schema_signature}, previous_signature={decision.previous_signature})"
    )
    drop_app_tables()
    init_schema()
    seed_mysql_from_json(SEED_DATA_PATH, truncate=False)
    ensure_state_table()
    set_state_value(STATE_KEY_SCHEMA_SIGNATURE, schema_signature)
    print(f"Demo bootstrap complete: stored schema signature {schema_signature}")
    return decision


def main() -> None:
    run_demo_bootstrap()


if __name__ == "__main__":
    main()
