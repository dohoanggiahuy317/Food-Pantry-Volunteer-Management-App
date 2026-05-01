"""
DB Component Tests

Tests MySQLBackend directly against a real MySQL instance running in the
docker-compose.test.yml container. No mocks — MySQL IS the component under test.

Run with: pytest tests/component/test_db_component.py -v -m component
"""
from __future__ import annotations

import os
import pytest
import mysql.connector
from mysql.connector import IntegrityError

pytestmark = pytest.mark.component


# ── Helpers ───────────────────────────────────────────────────────────────────

def _raw_conn():
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ["MYSQL_PORT"]),
        database=os.environ["MYSQL_DATABASE"],
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
    )


def _make_user(db, *, name="Test User", email="user@example.com",
               phone="555-0100", roles=None):
    return db.create_user(
        full_name=name,
        email=email,
        phone_number=phone,
        roles=roles or ["VOLUNTEER"],
    )


def _make_pantry(db, *, name="Test Pantry", address="123 Main St"):
    return db.create_pantry(name, address, lead_ids=[])


def _make_shift(db, pantry_id, user_id, *, name="Morning Distribution"):
    return db.create_shift(
        pantry_id=pantry_id,
        shift_name=name,
        start_time="2026-09-01T09:00:00Z",
        end_time="2026-09-01T12:00:00Z",
        status="OPEN",
        created_by=user_id,
    )


def _make_role(db, shift_id, *, title="Packer", required=3):
    return db.create_shift_role(shift_id, title, required)


# ── Schema Tests ──────────────────────────────────────────────────────────────

class TestSchema:
    EXPECTED_TABLES = {
        "roles",
        "users",
        "user_roles",
        "pantries",
        "pantry_leads",
        "pantry_subscriptions",
        "shift_series",
        "shifts",
        "shift_roles",
        "shift_signups",
        "help_broadcasts",
    }

    def test_all_expected_tables_exist(self, mysql_schema):
        conn = _raw_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s",
            (os.environ["MYSQL_DATABASE"],),
        )
        found = {row[0] for row in cur.fetchall()}
        conn.close()
        assert self.EXPECTED_TABLES.issubset(found), (
            f"Missing tables: {self.EXPECTED_TABLES - found}"
        )

    def test_roles_table_seeded_with_system_roles(self, mysql_schema):
        conn = _raw_conn()
        cur = conn.cursor()
        cur.execute("SELECT role_name FROM roles")
        names = {row[0] for row in cur.fetchall()}
        conn.close()
        assert {"VOLUNTEER", "PANTRY_LEAD", "ADMIN", "SUPER_ADMIN"}.issubset(names)

    # def test_init_schema_is_idempotent(self, mysql_schema):
    #     from db.init_schema import init_schema
    #     init_schema()  # second call — should not raise or duplicate data
    #     conn = _raw_conn()
    #     cur = conn.cursor()
    #     cur.execute(
    #         "SELECT COUNT(*) FROM information_schema.TABLES "
    #         "WHERE TABLE_SCHEMA = %s",
    #         (os.environ["MYSQL_DATABASE"],),
    #     )
    #     count = cur.fetchone()[0]
    #     conn.close()
    #     assert count == len(self.EXPECTED_TABLES)


# ── User CRUD Tests ───────────────────────────────────────────────────────────

class TestUserCRUD:
    def test_create_user_persists_to_mysql(self, clean_db, db_backend):
        user = _make_user(db_backend)
        assert isinstance(user["user_id"], int)
        assert user["user_id"] > 0
        assert user["email"] == "user@example.com"
        assert user["full_name"] == "Test User"

    def test_get_user_by_id_returns_same_data(self, clean_db, db_backend):
        created = _make_user(db_backend)
        fetched = db_backend.get_user_by_id(created["user_id"])
        assert fetched is not None
        assert fetched["user_id"] == created["user_id"]
        assert fetched["email"] == created["email"]

    def test_get_user_by_id_returns_none_for_missing(self, clean_db, db_backend):
        assert db_backend.get_user_by_id(99999) is None

    def test_get_user_by_email(self, clean_db, db_backend):
        created = _make_user(db_backend, email="find@example.com")
        fetched = db_backend.get_user_by_email("find@example.com")
        assert fetched is not None
        assert fetched["user_id"] == created["user_id"]

    def test_get_user_by_email_is_case_insensitive(self, clean_db, db_backend):
        _make_user(db_backend, email="lower@example.com")
        fetched = db_backend.get_user_by_email("LOWER@EXAMPLE.COM")
        assert fetched is not None
        assert fetched["email"] == "lower@example.com"

    def test_duplicate_email_raises(self, clean_db, db_backend):
        _make_user(db_backend, email="dup@example.com")
        with pytest.raises(Exception):
            _make_user(db_backend, email="dup@example.com", name="Other")

    def test_update_user_persists(self, clean_db, db_backend):
        user = _make_user(db_backend)
        db_backend.update_user(user["user_id"], {"full_name": "Updated Name"})
        fetched = db_backend.get_user_by_id(user["user_id"])
        assert fetched["full_name"] == "Updated Name"

    def test_delete_user_removes_row(self, clean_db, db_backend):
        user = _make_user(db_backend)
        uid = user["user_id"]
        db_backend.delete_user(uid)
        assert db_backend.get_user_by_id(uid) is None

    def test_delete_user_cascades_to_user_roles(self, clean_db, db_backend):
        user = _make_user(db_backend, roles=["VOLUNTEER"])
        uid = user["user_id"]
        db_backend.delete_user(uid)
        conn = _raw_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_roles WHERE user_id = %s", (uid,))
        count = cur.fetchone()[0]
        conn.close()
        assert count == 0

    def test_list_users_returns_created_user(self, clean_db, db_backend):
        _make_user(db_backend, email="listed@example.com", name="Listed User")
        users = db_backend.list_users()
        emails = [u["email"] for u in users]
        assert "listed@example.com" in emails


# ── Pantry CRUD Tests ─────────────────────────────────────────────────────────

class TestPantryCRUD:
    def test_create_pantry_and_retrieve(self, clean_db, db_backend):
        pantry = _make_pantry(db_backend, name="Elm St Pantry", address="1 Elm St")
        assert pantry["pantry_id"] > 0
        assert pantry["name"] == "Elm St Pantry"
        fetched = db_backend.get_pantry_by_id(pantry["pantry_id"])
        assert fetched is not None
        assert fetched["location_address"] == "1 Elm St"

    def test_get_pantry_by_id_returns_none_for_missing(self, clean_db, db_backend):
        assert db_backend.get_pantry_by_id(99999) is None

    def test_update_pantry_persists(self, clean_db, db_backend):
        pantry = _make_pantry(db_backend, name="Old Name")
        db_backend.update_pantry(pantry["pantry_id"], {"name": "New Name"})
        fetched = db_backend.get_pantry_by_id(pantry["pantry_id"])
        assert fetched["name"] == "New Name"

    def test_list_pantries_includes_created(self, clean_db, db_backend):
        _make_pantry(db_backend, name="Listed Pantry")
        pantries = db_backend.list_pantries()
        names = [p["name"] for p in pantries]
        assert "Listed Pantry" in names


# ── Shift and Shift Role Tests ────────────────────────────────────────────────

class TestShiftCRUD:
    def test_create_shift_and_retrieve(self, clean_db, db_backend):
        user = _make_user(db_backend)
        pantry = _make_pantry(db_backend)
        shift = _make_shift(db_backend, pantry["pantry_id"], user["user_id"])
        assert shift["shift_id"] > 0
        assert shift["shift_name"] == "Morning Distribution"
        assert shift["status"] == "OPEN"
        assert shift["pantry_id"] == pantry["pantry_id"]

    def test_get_shift_by_id_returns_none_for_missing(self, clean_db, db_backend):
        assert db_backend.get_shift_by_id(99999) is None

    def test_create_shift_role_and_retrieve(self, clean_db, db_backend):
        user = _make_user(db_backend)
        pantry = _make_pantry(db_backend)
        shift = _make_shift(db_backend, pantry["pantry_id"], user["user_id"])
        role = _make_role(db_backend, shift["shift_id"], title="Driver", required=2)
        assert role["shift_role_id"] > 0
        assert role["role_title"] == "Driver"
        assert role["required_count"] == 2
        assert role["filled_count"] == 0

    def test_list_shift_roles_returns_all_roles_for_shift(self, clean_db, db_backend):
        user = _make_user(db_backend)
        pantry = _make_pantry(db_backend)
        shift = _make_shift(db_backend, pantry["pantry_id"], user["user_id"])
        _make_role(db_backend, shift["shift_id"], title="Sorter")
        _make_role(db_backend, shift["shift_id"], title="Greeter")
        roles = db_backend.list_shift_roles(shift["shift_id"])
        titles = [r["role_title"] for r in roles]
        assert "Sorter" in titles
        assert "Greeter" in titles
        assert len(roles) == 2

    def test_cancel_shift_updates_status(self, clean_db, db_backend):
        user = _make_user(db_backend)
        pantry = _make_pantry(db_backend)
        shift = _make_shift(db_backend, pantry["pantry_id"], user["user_id"])
        db_backend.update_shift(shift["shift_id"], {"status": "CANCELLED"})
        fetched = db_backend.get_shift_by_id(shift["shift_id"])
        assert fetched["status"] == "CANCELLED"

    def test_delete_shift_removes_row(self, clean_db, db_backend):
        user = _make_user(db_backend)
        pantry = _make_pantry(db_backend)
        shift = _make_shift(db_backend, pantry["pantry_id"], user["user_id"])
        sid = shift["shift_id"]
        db_backend.delete_shift(sid)
        assert db_backend.get_shift_by_id(sid) is None


# ── Signup Tests ──────────────────────────────────────────────────────────────

class TestSignups:
    def _setup(self, db):
        user = _make_user(db)
        pantry = _make_pantry(db)
        shift = _make_shift(db, pantry["pantry_id"], user["user_id"])
        role = _make_role(db, shift["shift_id"], required=2)
        return user, shift, role

    def test_create_signup_inserts_record(self, clean_db, db_backend):
        user, _, role = self._setup(db_backend)
        signup = db_backend.create_signup(role["shift_role_id"], user["user_id"], "CONFIRMED")
        assert signup["signup_id"] > 0
        assert signup["signup_status"] == "CONFIRMED"
        assert signup["user_id"] == user["user_id"]

    def test_create_signup_increments_filled_count(self, clean_db, db_backend):
        user, _, role = self._setup(db_backend)
        db_backend.create_signup(role["shift_role_id"], user["user_id"], "CONFIRMED")
        updated_role = db_backend.get_shift_role_by_id(role["shift_role_id"])
        assert updated_role["filled_count"] == 1

    def test_list_shift_signups_returns_created_signup(self, clean_db, db_backend):
        user, _, role = self._setup(db_backend)
        db_backend.create_signup(role["shift_role_id"], user["user_id"], "CONFIRMED")
        signups = db_backend.list_shift_signups(role["shift_role_id"])
        assert len(signups) == 1
        assert signups[0]["user_id"] == user["user_id"]

    def test_capacity_full_raises_runtime_error(self, clean_db, db_backend):
        pantry = _make_pantry(db_backend)
        shift = _make_shift(db_backend, pantry["pantry_id"],
                            _make_user(db_backend, email="lead@example.com")["user_id"])
        role = _make_role(db_backend, shift["shift_id"], required=1)

        user_a = _make_user(db_backend, email="a@example.com")
        user_b = _make_user(db_backend, email="b@example.com")

        db_backend.create_signup(role["shift_role_id"], user_a["user_id"], "CONFIRMED")
        with pytest.raises(RuntimeError, match="full"):
            db_backend.create_signup(role["shift_role_id"], user_b["user_id"], "CONFIRMED")

    def test_duplicate_signup_raises_value_error(self, clean_db, db_backend):
        user, _, role = self._setup(db_backend)
        db_backend.create_signup(role["shift_role_id"], user["user_id"], "CONFIRMED")
        with pytest.raises(ValueError, match="Already signed up"):
            db_backend.create_signup(role["shift_role_id"], user["user_id"], "CONFIRMED")

    def test_delete_signup_decrements_filled_count(self, clean_db, db_backend):
        user, _, role = self._setup(db_backend)
        signup = db_backend.create_signup(role["shift_role_id"], user["user_id"], "CONFIRMED")
        db_backend.delete_signup(signup["signup_id"])
        updated_role = db_backend.get_shift_role_by_id(role["shift_role_id"])
        assert updated_role["filled_count"] == 0

    def test_delete_signup_removes_record(self, clean_db, db_backend):
        user, _, role = self._setup(db_backend)
        signup = db_backend.create_signup(role["shift_role_id"], user["user_id"], "CONFIRMED")
        sid = signup["signup_id"]
        db_backend.delete_signup(sid)
        assert db_backend.get_signup_by_id(sid) is None

    def test_pending_signup_sets_reservation_expiry(self, clean_db, db_backend):
        user, _, role = self._setup(db_backend)
        signup = db_backend.create_signup(
            role["shift_role_id"], user["user_id"], "PENDING_CONFIRMATION"
        )
        # create_signup returns only (signup_id, shift_role_id, user_id,
        # signup_status, created_at); fetch the persisted row to check the expiry
        fetched = db_backend.get_signup_by_id(signup["signup_id"])
        assert fetched["reservation_expires_at"] is not None


# ── Shift Series Tests ────────────────────────────────────────────────────────

class TestShiftSeries:
    def test_create_shift_series_stores_correct_fields(self, clean_db, db_backend):
        user = _make_user(db_backend)
        pantry = _make_pantry(db_backend)
        series = db_backend.create_shift_series({
            "pantry_id": pantry["pantry_id"],
            "created_by": user["user_id"],
            "timezone": "America/New_York",
            "frequency": "WEEKLY",
            "interval_weeks": 1,
            "weekdays_csv": "MO,WE",
            "end_mode": "COUNT",
            "occurrence_count": 4,
        })
        assert series["shift_series_id"] > 0
        assert series["weekdays_csv"] == "MO,WE"
        assert series["end_mode"] == "COUNT"
        assert series["occurrence_count"] == 4
        assert series["interval_weeks"] == 1

    def test_create_shift_series_until_date_mode(self, clean_db, db_backend):
        user = _make_user(db_backend)
        pantry = _make_pantry(db_backend)
        series = db_backend.create_shift_series({
            "pantry_id": pantry["pantry_id"],
            "created_by": user["user_id"],
            "timezone": "America/Chicago",
            "frequency": "WEEKLY",
            "interval_weeks": 2,
            "weekdays_csv": "FR",
            "end_mode": "UNTIL",
            "until_date": "2026-12-31",
        })
        assert series["end_mode"] == "UNTIL"
        assert series["until_date"] == "2026-12-31"
        assert series["interval_weeks"] == 2

    def test_get_shift_series_by_id(self, clean_db, db_backend):
        user = _make_user(db_backend)
        pantry = _make_pantry(db_backend)
        created = db_backend.create_shift_series({
            "pantry_id": pantry["pantry_id"],
            "created_by": user["user_id"],
            "timezone": "UTC",
            "frequency": "WEEKLY",
            "interval_weeks": 1,
            "weekdays_csv": "TU",
            "end_mode": "COUNT",
            "occurrence_count": 2,
        })
        fetched = db_backend.get_shift_series_by_id(created["shift_series_id"])
        assert fetched is not None
        assert fetched["shift_series_id"] == created["shift_series_id"]

    def test_shifts_linked_to_series_are_retrievable(self, clean_db, db_backend):
        user = _make_user(db_backend)
        pantry = _make_pantry(db_backend)
        series = db_backend.create_shift_series({
            "pantry_id": pantry["pantry_id"],
            "created_by": user["user_id"],
            "timezone": "UTC",
            "frequency": "WEEKLY",
            "interval_weeks": 1,
            "weekdays_csv": "MO",
            "end_mode": "COUNT",
            "occurrence_count": 3,
        })
        for i in range(3):
            db_backend.create_shift(
                pantry_id=pantry["pantry_id"],
                shift_name="Weekly Distribution",
                start_time=f"2026-10-{5 + i * 7:02d}T09:00:00Z",
                end_time=f"2026-10-{5 + i * 7:02d}T12:00:00Z",
                status="OPEN",
                created_by=user["user_id"],
                shift_series_id=series["shift_series_id"],
                series_position=i + 1,
            )
        linked = db_backend.list_shifts_by_series(series["shift_series_id"])
        assert len(linked) == 3
        for shift in linked:
            assert shift["shift_series_id"] == series["shift_series_id"]


# ── Cascade Delete Tests ──────────────────────────────────────────────────────

class TestCascadeDeletes:
    def test_delete_shift_cascades_to_shift_roles(self, clean_db, db_backend):
        user = _make_user(db_backend)
        pantry = _make_pantry(db_backend)
        shift = _make_shift(db_backend, pantry["pantry_id"], user["user_id"])
        role = _make_role(db_backend, shift["shift_id"])
        rid = role["shift_role_id"]
        db_backend.delete_shift(shift["shift_id"])
        assert db_backend.get_shift_role_by_id(rid) is None

    def test_delete_shift_cascades_to_signups(self, clean_db, db_backend):
        user = _make_user(db_backend)
        pantry = _make_pantry(db_backend)
        shift = _make_shift(db_backend, pantry["pantry_id"], user["user_id"])
        role = _make_role(db_backend, shift["shift_id"])
        signup = db_backend.create_signup(role["shift_role_id"], user["user_id"], "CONFIRMED")
        signup_id = signup["signup_id"]
        db_backend.delete_shift(shift["shift_id"])
        assert db_backend.get_signup_by_id(signup_id) is None
