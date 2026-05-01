"""
Shared fixtures for component tests.

Environment variables MUST be set before any backend module is imported because
notifications.py captures RESEND_API_KEY and RESEND_FROM_EMAIL into module-level
constants at import time. The dotenv load below uses force=True to override any
values already present in the process environment.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Load .env.test before any backend import ──────────────────────────────────
_env_test = Path(__file__).resolve().parents[2] / ".env.test"
if _env_test.exists():
    from dotenv import dotenv_values
    for _k, _v in dotenv_values(_env_test).items():
        if _v is not None:
            os.environ[_k] = _v  # force-set, not setdefault

_backend_path = Path(__file__).resolve().parents[2] / "backend"
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))
# ──────────────────────────────────────────────────────────────────────────────

import mysql.connector  # noqa: E402 — must come after path setup


# ── FK-safe truncation order (child tables before parent tables) ───────────────
_TRUNCATE_ORDER = [
    "shift_signups",
    "shift_roles",
    "help_broadcasts",      # FK refs shifts.shift_id and users.user_id
    "shifts",
    "shift_series",
    "pantry_subscriptions",
    "pantry_leads",
    "pantries",
    "user_roles",
    "users",
]


def _raw_connection() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ["MYSQL_PORT"]),
        database=os.environ["MYSQL_DATABASE"],
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
    )


# ── Schema — run migrations once per session ──────────────────────────────────

@pytest.fixture(scope="session")
def mysql_schema():
    """Run schema migrations and seed static role data once for the entire test session."""
    from db.init_schema import init_schema
    init_schema()
    # init_schema() only creates tables; roles are seeded separately in production
    # by demo_bootstrap / seed_mysql_from_json. Reproduce that here.
    conn = _raw_connection()
    cur = conn.cursor()
    for role_id, role_name in [
        (0, "SUPER_ADMIN"),
        (1, "ADMIN"),
        (2, "PANTRY_LEAD"),
        (3, "VOLUNTEER"),
    ]:
        cur.execute(
            "INSERT INTO roles (role_id, role_name) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE role_name = VALUES(role_name)",
            (role_id, role_name),
        )
    conn.commit()
    cur.close()
    conn.close()


# ── Per-test data isolation ───────────────────────────────────────────────────

@pytest.fixture
def clean_db(mysql_schema):
    """Truncate all data tables before each test that requests this fixture."""
    conn = _raw_connection()
    cur = conn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    for table in _TRUNCATE_ORDER:
        cur.execute(f"TRUNCATE TABLE `{table}`")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()
    cur.close()
    conn.close()


# ── Database backend — session-scoped ─────────────────────────────────────────

@pytest.fixture(scope="session")
def db_backend(mysql_schema):
    """Session-scoped MySQLBackend instance for DB component tests."""
    from backends.mysql_backend import MySQLBackend
    return MySQLBackend()


# ── Firebase mock ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_firebase_verify():
    """
    Patches the two Firebase Admin SDK hooks that would otherwise make network
    calls or require real credentials:

    1. firebase_admin._apps  — faked as non-empty so FirebaseAuthService.__init__
       skips the credentials.Certificate / initialize_app branch entirely.
    2. firebase_admin.auth.verify_id_token — the actual token verification call,
       replaced with a configurable MagicMock.

    Tests that need different token payloads can set mock_firebase_verify.return_value
    or mock_firebase_verify.side_effect after receiving the fixture.
    """
    fake_apps = {"[DEFAULT]": MagicMock()}
    with patch("firebase_admin._apps", fake_apps), \
         patch("firebase_admin.auth.verify_id_token") as mock_verify:
        mock_verify.return_value = {
            "uid": "test-firebase-uid-123",
            "email": "volunteer@example.com",
            "email_verified": True,
            "name": "Test Volunteer",
        }
        yield mock_verify


# ── Resend mock ───────────────────────────────────────────────────────────────

@pytest.fixture
def mock_resend_send():
    """
    Patches resend.Emails.send so no real HTTP call is ever made.
    Tests inspect mock_resend_send.call_args to assert on the email payload.
    """
    with patch("resend.Emails.send") as mock_send:
        mock_send.return_value = {"id": "mock-email-id-abc123"}
        yield mock_send
