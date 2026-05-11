"""
Comprehensive Flask route tests using the in-memory backend.

All tests depend on ``reset_backend`` so each starts from the seed-data
snapshot at backend/data/in_memory.json.

Notes:
- Seed volunteers (user 6-27) are ALL rate-limited in the seed data because
  several of their signup ``created_at`` timestamps fall within the current 24h
  window (seed data covers 2026-04-27 to 2026-06-xx, today is 2026-04-29).
  For signup tests use ``_fresh_volunteer()`` to create a user with no history.
- Routes under /api/ that are NOT in AUTH_EXEMPT_API_PATHS and don't start with
  /api/public/ require the caller to be logged in (401 otherwise), even when the
  route docstring says "no authorization required" (meaning no role check).

Seed constants from backend/data/in_memory.json:
  SUPER_ADMIN_ID=1  – SUPER_ADMIN, leads pantry 1
  LEAD_ID=2         – PANTRY_LEAD, leads pantry 2
  LEAD_ID_4=25      – PANTRY_LEAD, leads pantry 4
  PANTRY_1=1, PANTRY_2=2, PANTRY_4=4
  SHIFT_P1_FUTURE=26  – pantry 1, 2026-05-05T13:00Z, series 1 pos 4
  SHIFT_P2_FUTURE=35  – pantry 2, 2026-04-29T17:30Z
  SHIFT_P4_FUTURE=20  – pantry 4, 2026-05-01T13:00Z
  ROLE_P1_OPEN=52     – shift 26, OPEN, required=2, filled=0
  ROLE_P1_51=51       – shift 26, OPEN, required=4, filled=2
  ROLE_P4_OPEN=39     – shift 20, OPEN, required=2, filled=1
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Seed constants
# ---------------------------------------------------------------------------
SUPER_ADMIN_ID = 1
LEAD_ID = 2
LEAD_ID_4 = 25
PANTRY_1 = 1
PANTRY_2 = 2
PANTRY_4 = 4
SHIFT_P1_FUTURE = 26
SHIFT_P2_FUTURE = 35
SHIFT_P4_FUTURE = 20
ROLE_P1_OPEN = 52    # shift 26, OPEN 0/2
ROLE_P1_51 = 51      # shift 26, OPEN 2/4
ROLE_P4_OPEN = 39    # shift 20, OPEN 1/2

# Module-level reference to the app module — set once by a session fixture so
# that other test files popping sys.modules["app"] on teardown don't break us.
_APP_MODULE = None


@pytest.fixture(scope="session", autouse=True)
def _store_app_ref(setup_backend):
    global _APP_MODULE
    _APP_MODULE, _ = setup_backend


class _FrozenRouteDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        frozen = cls(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
        if tz is not None:
            return frozen.astimezone(tz)
        return frozen.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _freeze_route_clock(monkeypatch, setup_backend):
    app_module, _ = setup_backend
    import backends.memory_backend as memory_backend

    monkeypatch.setattr(app_module, "datetime", _FrozenRouteDateTime)
    monkeypatch.setattr(memory_backend, "datetime", _FrozenRouteDateTime)


def _login(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _app():
    return _APP_MODULE


def _fresh_volunteer(suffix: str = ""):
    """Create a volunteer with no signup history (avoids rate limits)."""
    return _app().backend.create_user(
        full_name=f"Fresh Vol{suffix}",
        email=f"freshvol{suffix}@routes.test",
        phone_number="555-0000",
        roles=["VOLUNTEER"],
    )


# ---------------------------------------------------------------------------
# Health / pages
# ---------------------------------------------------------------------------
class TestHealthAndPages:
    def test_healthz(self, client, reset_backend):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.get_json()["status"] == "ok"

    def test_index(self, client, reset_backend):
        r = client.get("/")
        assert r.status_code == 200

    def test_dashboard(self, client, reset_backend):
        r = client.get("/dashboard")
        assert r.status_code == 200

    def test_options_skips_auth(self, client, reset_backend):
        r = client.options("/api/users")
        assert r.status_code != 401

    def test_non_api_path_no_auth_required(self, client, reset_backend):
        r = client.get("/healthz")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Auth config
# ---------------------------------------------------------------------------
class TestAuthConfig:
    def test_get_auth_config(self, client, reset_backend):
        r = client.get("/api/auth/config")
        assert r.status_code == 200
        data = r.get_json()
        assert "provider" in data


# ---------------------------------------------------------------------------
# Memory login
# ---------------------------------------------------------------------------
class TestLoginMemory:
    def test_login_admin_success(self, client, reset_backend):
        r = client.post("/api/auth/login/memory", json={"sample_account_id": "admin"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["next"] == "app"
        assert "user" in data

    def test_login_volunteer_success(self, client, reset_backend):
        r = client.post("/api/auth/login/memory", json={"sample_account_id": "volunteer"})
        assert r.status_code == 200

    def test_login_missing_account_id(self, client, reset_backend):
        r = client.post("/api/auth/login/memory", json={})
        assert r.status_code == 400

    def test_login_unknown_account(self, client, reset_backend):
        r = client.post("/api/auth/login/memory", json={"sample_account_id": "nonexistent"})
        assert r.status_code in (400, 404, 500)


# ---------------------------------------------------------------------------
# Google login/signup (disabled in memory mode)
# ---------------------------------------------------------------------------
class TestGoogleAuthDisabled:
    def test_login_google_wrong_mode(self, client, reset_backend):
        r = client.post("/api/auth/login/google", json={})
        assert r.status_code == 400
        assert "disabled" in r.get_json()["error"].lower()

    def test_signup_google_wrong_mode(self, client, reset_backend):
        r = client.post("/api/auth/signup/google", json={})
        assert r.status_code == 400
        assert "disabled" in r.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------
class TestLogout:
    def test_logout_unauthenticated(self, client, reset_backend):
        r = client.post("/api/auth/logout")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_logout_authenticated(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/auth/logout")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/me
# ---------------------------------------------------------------------------
class TestGetMe:
    def test_unauthenticated(self, client, reset_backend):
        r = client.get("/api/me")
        assert r.status_code == 401

    def test_authenticated(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/me")
        assert r.status_code == 200
        data = r.get_json()
        assert data["user_id"] == SUPER_ADMIN_ID
        assert "roles" in data

    def test_me_with_valid_timezone_header(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/me", headers={"X-Client-Timezone": "America/New_York"})
        assert r.status_code == 200

    def test_me_with_invalid_timezone_header(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/me", headers={"X-Client-Timezone": "Invalid/Zone"})
        assert r.status_code == 200

    def test_me_matching_timezone_no_update(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        client.get("/api/me", headers={"X-Client-Timezone": "America/Chicago"})
        r = client.get("/api/me", headers={"X-Client-Timezone": "America/Chicago"})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /api/me
# ---------------------------------------------------------------------------
class TestUpdateMe:
    def test_unauthenticated(self, client, reset_backend):
        r = client.patch("/api/me", json={"full_name": "New Name"})
        assert r.status_code == 401

    def test_update_full_name(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/me", json={"full_name": "Updated Admin"})
        assert r.status_code == 200
        assert r.get_json()["full_name"] == "Updated Admin"

    def test_update_phone_number(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/me", json={"phone_number": "555-9999"})
        assert r.status_code == 200

    def test_clear_phone_number(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/me", json={"phone_number": ""})
        assert r.status_code == 200

    def test_update_timezone(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/me", json={"timezone": "America/Chicago"})
        assert r.status_code == 200

    def test_empty_full_name_rejected(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/me", json={"full_name": ""})
        assert r.status_code == 400

    def test_no_valid_fields(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/me", json={"unknown_field": "value"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/me/email-change/prepare
# ---------------------------------------------------------------------------
class TestPrepareEmailChange:
    def test_unauthenticated(self, client, reset_backend):
        r = client.post("/api/me/email-change/prepare", json={"new_email": "x@x.com"})
        assert r.status_code == 401

    def test_wrong_auth_mode_returns_400(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/me/email-change/prepare", json={"new_email": "x@x.com"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /api/me
# ---------------------------------------------------------------------------
class TestDeleteMe:
    def test_unauthenticated(self, client, reset_backend):
        r = client.delete("/api/me")
        assert r.status_code == 401

    def test_protected_super_admin_cannot_delete(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.delete("/api/me")
        assert r.status_code == 403

    def test_volunteer_can_delete_self(self, client, reset_backend):
        vol = _app().backend.create_user(
            full_name="To Delete",
            email="todelete_routes@test.com",
            phone_number="555-0001",
            roles=["VOLUNTEER"],
        )
        _login(client, int(vol["user_id"]))
        r = client.delete("/api/me")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/users
# ---------------------------------------------------------------------------
class TestListUsers:
    def test_unauthenticated(self, client, reset_backend):
        r = client.get("/api/users")
        assert r.status_code == 401

    def test_lead_forbidden(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.get("/api/users")
        assert r.status_code == 403

    def test_admin_can_list(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/users")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_admin_list_with_role_filter(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/users?role=VOLUNTEER")
        assert r.status_code == 200
        users = r.get_json()
        assert all("VOLUNTEER" in u["roles"] for u in users)

    def test_admin_list_with_query(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/users?q=ben")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/users/<id>
# ---------------------------------------------------------------------------
class TestGetUser:
    def test_admin_can_get_user(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get(f"/api/users/{LEAD_ID}")
        assert r.status_code == 200
        assert r.get_json()["user_id"] == LEAD_ID

    def test_lead_forbidden(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.get(f"/api/users/{SUPER_ADMIN_ID}")
        assert r.status_code == 403

    def test_user_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/users/99999")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/users/<id>/signups
# ---------------------------------------------------------------------------
class TestListUserSignups:
    def test_admin_can_view_user_signups(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get(f"/api/users/{LEAD_ID}/signups")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_lead_cannot_view_others_signups(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.get(f"/api/users/{SUPER_ADMIN_ID}/signups")
        assert r.status_code == 403

    def test_user_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/users/99999/signups")
        assert r.status_code == 404

    def test_unauthenticated(self, client, reset_backend):
        r = client.get(f"/api/users/{LEAD_ID}/signups")
        assert r.status_code == 401

    def test_self_can_view_own_signups(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get(f"/api/users/{SUPER_ADMIN_ID}/signups")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/roles
# ---------------------------------------------------------------------------
class TestListRoles:
    def test_unauthenticated(self, client, reset_backend):
        r = client.get("/api/roles")
        assert r.status_code == 401

    def test_authenticated_returns_roles(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/roles")
        assert r.status_code == 200
        roles = r.get_json()
        assert len(roles) >= 4


# ---------------------------------------------------------------------------
# POST /api/users
# ---------------------------------------------------------------------------
class TestCreateUser:
    def test_admin_can_create(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/users", json={
            "full_name": "New Vol Routes",
            "email": "newvol_routes@test.com",
            "roles": ["VOLUNTEER"],
        })
        assert r.status_code == 201
        assert r.get_json()["email"] == "newvol_routes@test.com"

    def test_lead_forbidden(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.post("/api/users", json={"full_name": "X", "email": "x@x.com"})
        assert r.status_code == 403

    def test_missing_required_fields(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/users", json={"full_name": "No Email"})
        assert r.status_code == 400

    def test_too_many_roles(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/users", json={
            "full_name": "X",
            "email": "x2_routes@test.com",
            "roles": ["VOLUNTEER", "PANTRY_LEAD"],
        })
        assert r.status_code == 400

    def test_cannot_assign_super_admin(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/users", json={
            "full_name": "X",
            "email": "x3_routes@test.com",
            "roles": ["SUPER_ADMIN"],
        })
        assert r.status_code == 403

    def test_duplicate_email_rejected(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/users", json={
            "full_name": "Dup",
            "email": "ben@volunteer.org",
            "roles": ["VOLUNTEER"],
        })
        assert r.status_code == 400

    def test_create_user_with_timezone(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/users", json={
            "full_name": "TZ User Routes",
            "email": "tzuser_routes@test.com",
            "timezone": "Europe/London",
            "roles": ["VOLUNTEER"],
        })
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# PATCH /api/users/<id>/roles
# ---------------------------------------------------------------------------
class TestReplaceUserRoles:
    def test_admin_can_set_role(self, client, reset_backend):
        vol = _fresh_volunteer("_roles1")
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/users/{vol['user_id']}/roles", json={"role_ids": [3]})
        assert r.status_code == 200

    def test_unauthenticated(self, client, reset_backend):
        r = client.patch(f"/api/users/{LEAD_ID}/roles", json={"role_ids": [3]})
        assert r.status_code == 401

    def test_lead_forbidden(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.patch(f"/api/users/{LEAD_ID}/roles", json={"role_ids": [3]})
        assert r.status_code == 403

    def test_user_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/users/99999/roles", json={"role_ids": [3]})
        assert r.status_code == 404

    def test_role_ids_not_array(self, client, reset_backend):
        vol = _fresh_volunteer("_roles2")
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/users/{vol['user_id']}/roles", json={"role_ids": "VOLUNTEER"})
        assert r.status_code == 400

    def test_multiple_roles_rejected(self, client, reset_backend):
        vol = _fresh_volunteer("_roles3")
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/users/{vol['user_id']}/roles", json={"role_ids": [2, 3]})
        assert r.status_code == 400

    def test_super_admin_protected(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/users/{SUPER_ADMIN_ID}/roles", json={"role_ids": [3]})
        assert r.status_code == 403

    def test_unknown_role_id(self, client, reset_backend):
        vol = _fresh_volunteer("_roles4")
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/users/{vol['user_id']}/roles", json={"role_ids": [999]})
        assert r.status_code == 400

    def test_cannot_assign_super_admin_role(self, client, reset_backend):
        vol = _fresh_volunteer("_roles5")
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/users/{vol['user_id']}/roles", json={"role_ids": [0]})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Pantry routes
# ---------------------------------------------------------------------------
class TestPantryRoutes:
    def test_list_pantries_admin(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/pantries")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_list_pantries_lead(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.get("/api/pantries")
        assert r.status_code == 200

    def test_list_all_pantries_requires_auth(self, client, reset_backend):
        r = client.get("/api/all_pantries")
        assert r.status_code == 401

    def test_list_all_pantries_authenticated(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/all_pantries")
        assert r.status_code == 200
        assert len(r.get_json()) > 0

    def test_get_pantry_requires_auth(self, client, reset_backend):
        r = client.get(f"/api/pantries/{PANTRY_1}")
        assert r.status_code == 401

    def test_get_pantry_authenticated(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get(f"/api/pantries/{PANTRY_1}")
        assert r.status_code == 200
        assert r.get_json()["pantry_id"] == PANTRY_1

    def test_get_pantry_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/pantries/99999")
        assert r.status_code == 404

    def test_create_pantry_admin(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/pantries", json={
            "name": "Test Routes Pantry",
            "location_address": "123 Test St",
        })
        assert r.status_code == 201

    def test_create_pantry_missing_fields(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/pantries", json={"name": "Only Name"})
        assert r.status_code == 400

    def test_create_pantry_forbidden_lead(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.post("/api/pantries", json={"name": "X", "location_address": "Y"})
        assert r.status_code == 403

    def test_create_pantry_with_lead_ids(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/pantries", json={
            "name": "Leads Pantry Routes",
            "location_address": "456 Lead St",
            "lead_ids": [LEAD_ID],
        })
        assert r.status_code == 201

    def test_update_pantry_admin(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/pantries/{PANTRY_1}", json={"name": "Updated Name Routes"})
        assert r.status_code == 200
        assert r.get_json()["name"] == "Updated Name Routes"

    def test_update_pantry_no_valid_fields(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/pantries/{PANTRY_1}", json={"unknown": "x"})
        assert r.status_code == 400

    def test_update_pantry_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/pantries/99999", json={"name": "X"})
        assert r.status_code == 404

    def test_delete_pantry_admin(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/pantries", json={"name": "ToDelete_Routes", "location_address": "Addr"})
        pid = r.get_json()["pantry_id"]
        r2 = client.delete(f"/api/pantries/{pid}")
        assert r2.status_code == 200

    def test_delete_pantry_forbidden_lead(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.delete(f"/api/pantries/{PANTRY_1}")
        assert r.status_code == 403

    def test_delete_pantry_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.delete("/api/pantries/99999")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Pantry leads
# ---------------------------------------------------------------------------
class TestPantryLeads:
    def test_add_lead_already_lead(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_2}/leads", json={"user_id": LEAD_ID})
        assert r.status_code == 400

    def test_add_lead_missing_user_id(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/leads", json={})
        assert r.status_code == 400

    def test_add_lead_not_a_pantry_lead_role(self, client, reset_backend):
        vol = _fresh_volunteer("_lead1")
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/leads", json={"user_id": vol["user_id"]})
        assert r.status_code == 400

    def test_add_lead_pantry_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/pantries/99999/leads", json={"user_id": LEAD_ID_4})
        assert r.status_code == 404

    def test_add_lead_success(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/leads", json={"user_id": LEAD_ID_4})
        assert r.status_code == 201

    def test_remove_pantry_lead(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.delete(f"/api/pantries/{PANTRY_2}/leads/{LEAD_ID}")
        assert r.status_code == 200

    def test_remove_lead_pantry_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.delete(f"/api/pantries/99999/leads/{LEAD_ID}")
        assert r.status_code == 404

    def test_remove_lead_user_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.delete(f"/api/pantries/{PANTRY_1}/leads/99999")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Volunteer pantry routes
# ---------------------------------------------------------------------------
class TestVolunteerPantryRoutes:
    def test_list_volunteer_pantries(self, client, reset_backend):
        vol = _fresh_volunteer("_vp1")
        _login(client, vol["user_id"])
        r = client.get("/api/volunteer/pantries")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_list_volunteer_pantries_lead_forbidden(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.get("/api/volunteer/pantries")
        assert r.status_code == 403

    def test_list_volunteer_pantries_admin_forbidden(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/volunteer/pantries")
        assert r.status_code == 403

    def test_subscribe_to_pantry(self, client, reset_backend):
        vol = _fresh_volunteer("_vp2")
        _login(client, vol["user_id"])
        r = client.post(f"/api/pantries/{PANTRY_1}/subscribe")
        assert r.status_code == 200
        assert r.get_json()["is_subscribed"] is True

    def test_subscribe_pantry_not_found(self, client, reset_backend):
        vol = _fresh_volunteer("_vp3")
        _login(client, vol["user_id"])
        r = client.post("/api/pantries/99999/subscribe")
        assert r.status_code == 404

    def test_unsubscribe_from_pantry(self, client, reset_backend):
        vol = _fresh_volunteer("_vp4")
        _login(client, vol["user_id"])
        client.post(f"/api/pantries/{PANTRY_1}/subscribe")
        r = client.delete(f"/api/pantries/{PANTRY_1}/subscribe")
        assert r.status_code == 200
        assert r.get_json()["is_subscribed"] is False

    def test_unsubscribe_pantry_not_found(self, client, reset_backend):
        vol = _fresh_volunteer("_vp5")
        _login(client, vol["user_id"])
        r = client.delete("/api/pantries/99999/subscribe")
        assert r.status_code == 404

    def test_subscribe_as_non_volunteer_forbidden(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/subscribe")
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Shift listing routes
# ---------------------------------------------------------------------------
class TestShiftListingRoutes:
    def test_get_shifts_for_pantry_admin(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get(f"/api/pantries/{PANTRY_1}/shifts")
        assert r.status_code == 200
        assert len(r.get_json()) > 0

    def test_get_shifts_requires_auth(self, client, reset_backend):
        r = client.get(f"/api/pantries/{PANTRY_1}/shifts")
        assert r.status_code == 401

    def test_get_active_shifts_requires_auth(self, client, reset_backend):
        r = client.get(f"/api/pantries/{PANTRY_1}/active-shifts")
        assert r.status_code == 401

    def test_get_active_shifts(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get(f"/api/pantries/{PANTRY_1}/active-shifts")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_get_calendar_shifts_requires_auth(self, client, reset_backend):
        r = client.get("/api/calendar/shifts?start=2026-05-01T00:00:00Z&end=2026-06-01T00:00:00Z")
        assert r.status_code == 401

    def test_get_calendar_shifts(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/calendar/shifts?start=2026-05-01T00:00:00Z&end=2026-06-01T00:00:00Z")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_get_calendar_shifts_includes_past_range_shift(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        past_shift = _app().backend.create_shift(
            pantry_id=PANTRY_1,
            shift_name="Past Calendar Route Shift",
            start_time="2026-04-01T10:00:00Z",
            end_time="2026-04-01T12:00:00Z",
            status="ACTIVE",
            created_by=SUPER_ADMIN_ID,
        )

        r = client.get("/api/calendar/shifts?start=2026-04-01T00:00:00Z&end=2026-04-02T00:00:00Z")

        assert r.status_code == 200
        shift_ids = [shift["shift_id"] for shift in r.get_json()]
        assert past_shift["shift_id"] in shift_ids

    def test_get_calendar_shifts_missing_params(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/calendar/shifts")
        assert r.status_code == 400

    def test_get_calendar_shifts_invalid_range(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/calendar/shifts?start=2026-06-01T00:00:00Z&end=2026-05-01T00:00:00Z")
        assert r.status_code == 400

    def test_get_single_shift_requires_auth(self, client, reset_backend):
        r = client.get(f"/api/shifts/{SHIFT_P1_FUTURE}")
        assert r.status_code == 401

    def test_get_single_shift_authenticated(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get(f"/api/shifts/{SHIFT_P1_FUTURE}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["shift_id"] == SHIFT_P1_FUTURE
        assert "recurrence" in data

    def test_get_single_shift_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/shifts/99999")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Create shift
# ---------------------------------------------------------------------------
class TestCreateShift:
    def test_admin_create_shift(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts", json={
            "shift_name": "Test Shift Routes",
            "start_time": "2027-01-10T10:00:00Z",
            "end_time": "2027-01-10T14:00:00Z",
        })
        assert r.status_code == 201
        assert r.get_json()["shift_name"] == "Test Shift Routes"

    def test_create_shift_missing_fields(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts", json={"shift_name": "X"})
        assert r.status_code == 400

    def test_create_shift_pantry_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/pantries/99999/shifts", json={
            "shift_name": "X",
            "start_time": "2027-01-01T10:00:00Z",
            "end_time": "2027-01-01T12:00:00Z",
        })
        assert r.status_code == 404

    def test_create_shift_unauthenticated(self, client, reset_backend):
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts", json={
            "shift_name": "X",
            "start_time": "2027-01-01T10:00:00Z",
            "end_time": "2027-01-01T12:00:00Z",
        })
        assert r.status_code == 401

    def test_create_shift_volunteer_forbidden(self, client, reset_backend):
        vol = _fresh_volunteer("_cs1")
        _login(client, vol["user_id"])
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts", json={
            "shift_name": "X",
            "start_time": "2027-01-01T10:00:00Z",
            "end_time": "2027-01-01T12:00:00Z",
        })
        assert r.status_code == 403

    def test_create_shift_lead_wrong_pantry(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts", json={
            "shift_name": "X",
            "start_time": "2027-01-01T10:00:00Z",
            "end_time": "2027-01-01T12:00:00Z",
        })
        assert r.status_code == 403

    def test_create_shift_lead_own_pantry(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.post(f"/api/pantries/{PANTRY_2}/shifts", json={
            "shift_name": "Lead's Shift Routes",
            "start_time": "2027-01-10T10:00:00Z",
            "end_time": "2027-01-10T14:00:00Z",
        })
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# Full-create shift (one-off and recurring)
# ---------------------------------------------------------------------------
class TestCreateFullShift:
    def test_create_oneoff_shift_with_roles(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "Full Create Routes",
            "start_time": "2027-03-15T10:00:00Z",
            "end_time": "2027-03-15T14:00:00Z",
            "roles": [{"role_title": "Helper", "required_count": 2}],
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data["created_shift_count"] == 1
        assert data["shift_series_id"] is None

    def test_create_recurring_shift_count(self, client, reset_backend):
        # 2027-03-08 is Monday (MO)
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "Weekly Routes Count",
            "start_time": "2027-03-08T10:00:00Z",
            "end_time": "2027-03-08T14:00:00Z",
            "roles": [{"role_title": "Helper", "required_count": 1}],
            "recurrence": {
                "timezone": "America/New_York",
                "frequency": "WEEKLY",
                "interval_weeks": 1,
                "weekdays": ["MO"],
                "end_mode": "COUNT",
                "occurrence_count": 3,
            },
        })
        assert r.status_code == 201
        data = r.get_json()
        assert data["created_shift_count"] == 3
        assert data["shift_series_id"] is not None

    def test_create_recurring_shift_until_date(self, client, reset_backend):
        # 2027-03-08 is Monday (MO)
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "Weekly Routes Until",
            "start_time": "2027-03-08T10:00:00Z",
            "end_time": "2027-03-08T14:00:00Z",
            "roles": [{"role_title": "Helper", "required_count": 1}],
            "recurrence": {
                "timezone": "America/New_York",
                "frequency": "WEEKLY",
                "interval_weeks": 1,
                "weekdays": ["MO"],
                "end_mode": "UNTIL",
                "until_date": "2027-04-01",
            },
        })
        assert r.status_code == 201

    def test_invalid_end_time_before_start(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "Bad Time",
            "start_time": "2027-03-15T14:00:00Z",
            "end_time": "2027-03-15T10:00:00Z",
            "roles": [{"role_title": "H", "required_count": 1}],
        })
        assert r.status_code == 400

    def test_invalid_recurrence_timezone(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "Bad TZ",
            "start_time": "2027-03-08T10:00:00Z",
            "end_time": "2027-03-08T14:00:00Z",
            "roles": [{"role_title": "H", "required_count": 1}],
            "recurrence": {
                "timezone": "Not/Valid",
                "frequency": "WEEKLY",
                "interval_weeks": 1,
                "weekdays": ["MO"],
                "end_mode": "COUNT",
                "occurrence_count": 2,
            },
        })
        assert r.status_code == 400

    def test_missing_roles_field(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "No Roles",
            "start_time": "2027-03-15T10:00:00Z",
            "end_time": "2027-03-15T14:00:00Z",
        })
        assert r.status_code == 400

    def test_forbidden_volunteer(self, client, reset_backend):
        vol = _fresh_volunteer("_cfs1")
        _login(client, vol["user_id"])
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "X",
            "start_time": "2027-03-15T10:00:00Z",
            "end_time": "2027-03-15T14:00:00Z",
            "roles": [{"role_title": "H", "required_count": 1}],
        })
        assert r.status_code == 403

    def test_pantry_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/pantries/99999/shifts/full-create", json={
            "shift_name": "X",
            "start_time": "2027-03-15T10:00:00Z",
            "end_time": "2027-03-15T14:00:00Z",
            "roles": [{"role_title": "H", "required_count": 1}],
        })
        assert r.status_code == 404

    def test_invalid_recurrence_weekday(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "Bad Day",
            "start_time": "2027-03-08T10:00:00Z",
            "end_time": "2027-03-08T14:00:00Z",
            "roles": [{"role_title": "H", "required_count": 1}],
            "recurrence": {
                "timezone": "America/New_York",
                "frequency": "WEEKLY",
                "interval_weeks": 1,
                "weekdays": ["BADDAY"],
                "end_mode": "COUNT",
                "occurrence_count": 2,
            },
        })
        assert r.status_code == 400

    def test_recurrence_weekday_not_matching_start(self, client, reset_backend):
        # Start is Monday but weekday is TU
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "Mismatch",
            "start_time": "2027-03-08T10:00:00Z",
            "end_time": "2027-03-08T14:00:00Z",
            "roles": [{"role_title": "H", "required_count": 1}],
            "recurrence": {
                "timezone": "America/New_York",
                "frequency": "WEEKLY",
                "interval_weeks": 1,
                "weekdays": ["TU"],
                "end_mode": "COUNT",
                "occurrence_count": 2,
            },
        })
        assert r.status_code == 400

    def test_recurrence_invalid_frequency(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "Bad Freq",
            "start_time": "2027-03-08T10:00:00Z",
            "end_time": "2027-03-08T14:00:00Z",
            "roles": [{"role_title": "H", "required_count": 1}],
            "recurrence": {
                "timezone": "America/New_York",
                "frequency": "DAILY",
                "interval_weeks": 1,
                "weekdays": ["MO"],
                "end_mode": "COUNT",
                "occurrence_count": 2,
            },
        })
        assert r.status_code == 400

    def test_recurrence_end_mode_invalid(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "Bad End",
            "start_time": "2027-03-08T10:00:00Z",
            "end_time": "2027-03-08T14:00:00Z",
            "roles": [{"role_title": "H", "required_count": 1}],
            "recurrence": {
                "timezone": "America/New_York",
                "frequency": "WEEKLY",
                "interval_weeks": 1,
                "weekdays": ["MO"],
                "end_mode": "FOREVER",
            },
        })
        assert r.status_code == 400

    def test_recurrence_invalid_interval(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "Bad Interval",
            "start_time": "2027-03-08T10:00:00Z",
            "end_time": "2027-03-08T14:00:00Z",
            "roles": [{"role_title": "H", "required_count": 1}],
            "recurrence": {
                "timezone": "America/New_York",
                "frequency": "WEEKLY",
                "interval_weeks": 0,
                "weekdays": ["MO"],
                "end_mode": "COUNT",
                "occurrence_count": 2,
            },
        })
        assert r.status_code == 400

    def test_role_required_count_invalid(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "Bad Role",
            "start_time": "2027-03-15T10:00:00Z",
            "end_time": "2027-03-15T14:00:00Z",
            "roles": [{"role_title": "H", "required_count": 0}],
        })
        assert r.status_code == 400

    def test_role_missing_title(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "No Title",
            "start_time": "2027-03-15T10:00:00Z",
            "end_time": "2027-03-15T14:00:00Z",
            "roles": [{"required_count": 2}],
        })
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Update shift (simple PATCH)
# ---------------------------------------------------------------------------
class TestUpdateShift:
    def test_admin_update_shift_name(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/shifts/{SHIFT_P1_FUTURE}", json={"shift_name": "Updated Routes"})
        assert r.status_code == 200
        assert r.get_json()["shift_name"] == "Updated Routes"

    def test_no_valid_fields(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/shifts/{SHIFT_P1_FUTURE}", json={"bogus": "val"})
        assert r.status_code == 400

    def test_unauthenticated(self, client, reset_backend):
        r = client.patch(f"/api/shifts/{SHIFT_P1_FUTURE}", json={"shift_name": "X"})
        assert r.status_code == 401

    def test_shift_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/shifts/99999", json={"shift_name": "X"})
        assert r.status_code == 404

    def test_volunteer_forbidden(self, client, reset_backend):
        vol = _fresh_volunteer("_us1")
        _login(client, vol["user_id"])
        r = client.patch(f"/api/shifts/{SHIFT_P1_FUTURE}", json={"shift_name": "X"})
        assert r.status_code == 403

    def test_cancel_shift_via_patch(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/shifts/{SHIFT_P1_FUTURE}", json={"status": "CANCELLED"})
        assert r.status_code == 200
        assert r.get_json()["status"] == "CANCELLED"

    def test_lead_can_update_own_pantry_shift(self, client, reset_backend):
        # Create a fresh future shift in pantry 2 so the test isn't tied to seed dates.
        _login(client, SUPER_ADMIN_ID)
        cr = client.post(f"/api/pantries/{PANTRY_2}/shifts/full-create", json={
            "shift_name": "Lead Test Shift",
            "start_time": "2028-01-01T10:00:00Z",
            "end_time": "2028-01-01T11:00:00Z",
            "roles": [{"role_title": "Helper", "required_count": 1}],
        })
        assert cr.status_code == 201
        new_shift_id = cr.get_json()["first_shift"]["shift_id"]
        _login(client, LEAD_ID)
        r = client.patch(f"/api/shifts/{new_shift_id}", json={"shift_name": "Lead Updated"})
        assert r.status_code == 200
        assert r.get_json()["shift_name"] == "Lead Updated"

    def test_lead_cannot_update_other_pantry_shift(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.patch(f"/api/shifts/{SHIFT_P1_FUTURE}", json={"shift_name": "X"})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Full-update shift (PUT)
# ---------------------------------------------------------------------------
class TestFullUpdateShift:
    def test_single_update(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.put(f"/api/shifts/{SHIFT_P1_FUTURE}/full-update", json={
            "shift_name": "Full Updated Routes",
            "start_time": "2026-05-05T13:00:00Z",
            "end_time": "2026-05-05T17:00:00Z",
            "roles": [{"role_title": "Helper", "required_count": 2}],
            "apply_scope": "single",
        })
        assert r.status_code == 200

    def test_future_scope_update_with_new_recurrence(self, client, reset_backend):
        # Shift 26 is a recurring (series 1). Update future with new recurrence.
        # Start must match the weekday. 2026-05-06 = Wednesday (WE).
        _login(client, SUPER_ADMIN_ID)
        r = client.put(f"/api/shifts/{SHIFT_P1_FUTURE}/full-update", json={
            "shift_name": "Future Updated Routes",
            "start_time": "2026-05-06T13:00:00Z",
            "end_time": "2026-05-06T17:00:00Z",
            "roles": [{"role_title": "Helper", "required_count": 2}],
            "apply_scope": "future",
            "recurrence": {
                "timezone": "America/New_York",
                "frequency": "WEEKLY",
                "interval_weeks": 1,
                "weekdays": ["WE"],
                "end_mode": "COUNT",
                "occurrence_count": 5,
            },
        })
        assert r.status_code == 200

    def test_future_scope_existing_recurrence(self, client, reset_backend):
        # No recurrence override: uses existing series recurrence. Shift 26 is TU.
        _login(client, SUPER_ADMIN_ID)
        r = client.put(f"/api/shifts/{SHIFT_P1_FUTURE}/full-update", json={
            "shift_name": "Future Same Recurrence Routes",
            "roles": [{"role_title": "Helper", "required_count": 2}],
            "apply_scope": "future",
        })
        assert r.status_code == 200

    def test_invalid_apply_scope(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.put(f"/api/shifts/{SHIFT_P1_FUTURE}/full-update", json={
            "roles": [{"role_title": "H", "required_count": 1}],
            "apply_scope": "all",
        })
        assert r.status_code == 400

    def test_future_scope_on_non_recurring_shift(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "OneOff Full Update",
            "start_time": "2027-06-10T10:00:00Z",
            "end_time": "2027-06-10T14:00:00Z",
            "roles": [{"role_title": "H", "required_count": 1}],
        })
        new_id = r.get_json()["first_shift"]["shift_id"]
        r2 = client.put(f"/api/shifts/{new_id}/full-update", json={
            "roles": [{"role_title": "H", "required_count": 1}],
            "apply_scope": "future",
        })
        assert r2.status_code == 400

    def test_unauthenticated(self, client, reset_backend):
        r = client.put(f"/api/shifts/{SHIFT_P1_FUTURE}/full-update", json={
            "roles": [{"role_title": "H", "required_count": 1}],
        })
        assert r.status_code == 401

    def test_shift_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.put("/api/shifts/99999/full-update", json={
            "roles": [{"role_title": "H", "required_count": 1}],
        })
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Delete/cancel shift
# ---------------------------------------------------------------------------
class TestDeleteShift:
    def test_cancel_via_delete(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.delete(f"/api/shifts/{SHIFT_P1_FUTURE}")
        assert r.status_code == 200
        assert r.get_json()["status"] == "CANCELLED"

    def test_unauthenticated(self, client, reset_backend):
        r = client.delete(f"/api/shifts/{SHIFT_P1_FUTURE}")
        assert r.status_code == 401

    def test_shift_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.delete("/api/shifts/99999")
        assert r.status_code == 404

    def test_volunteer_forbidden(self, client, reset_backend):
        vol = _fresh_volunteer("_ds1")
        _login(client, vol["user_id"])
        r = client.delete(f"/api/shifts/{SHIFT_P1_FUTURE}")
        assert r.status_code == 403


class TestCancelShiftScoped:
    def test_cancel_single(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P1_FUTURE}/cancel", json={"apply_scope": "single"})
        assert r.status_code == 200

    def test_cancel_future(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P1_FUTURE}/cancel", json={"apply_scope": "future"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["apply_scope"] == "future"

    def test_cancel_invalid_scope(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P1_FUTURE}/cancel", json={"apply_scope": "all"})
        assert r.status_code == 400

    def test_cancel_future_non_recurring_shift(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
            "shift_name": "OneOff Cancel",
            "start_time": "2027-07-10T10:00:00Z",
            "end_time": "2027-07-10T14:00:00Z",
            "roles": [{"role_title": "H", "required_count": 1}],
        })
        new_id = r.get_json()["first_shift"]["shift_id"]
        r2 = client.post(f"/api/shifts/{new_id}/cancel", json={"apply_scope": "future"})
        assert r2.status_code == 400

    def test_cancel_shift_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/shifts/99999/cancel", json={"apply_scope": "single"})
        assert r.status_code == 404

    def test_cancel_unauthenticated(self, client, reset_backend):
        r = client.post(f"/api/shifts/{SHIFT_P1_FUTURE}/cancel", json={"apply_scope": "single"})
        assert r.status_code == 401

    def test_cancel_volunteer_forbidden(self, client, reset_backend):
        vol = _fresh_volunteer("_css1")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shifts/{SHIFT_P1_FUTURE}/cancel", json={"apply_scope": "single"})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Shift registrations
# ---------------------------------------------------------------------------
class TestShiftRegistrations:
    def test_admin_get_registrations(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get(f"/api/shifts/{SHIFT_P1_FUTURE}/registrations")
        assert r.status_code == 200
        data = r.get_json()
        assert "roles" in data
        assert "shift_id" in data

    def test_unauthenticated(self, client, reset_backend):
        r = client.get(f"/api/shifts/{SHIFT_P1_FUTURE}/registrations")
        assert r.status_code == 401

    def test_volunteer_forbidden(self, client, reset_backend):
        vol = _fresh_volunteer("_sr1")
        _login(client, vol["user_id"])
        r = client.get(f"/api/shifts/{SHIFT_P1_FUTURE}/registrations")
        assert r.status_code == 403

    def test_shift_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/shifts/99999/registrations")
        assert r.status_code == 404

    def test_lead_can_see_own_pantry(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.get(f"/api/shifts/{SHIFT_P2_FUTURE}/registrations")
        assert r.status_code == 200

    def test_lead_cannot_see_other_pantry(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.get(f"/api/shifts/{SHIFT_P1_FUTURE}/registrations")
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Shift roles CRUD
# ---------------------------------------------------------------------------
class TestShiftRoleCRUD:
    def test_create_shift_role(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P1_FUTURE}/roles", json={
            "role_title": "New Role Routes",
            "required_count": 3,
        })
        assert r.status_code == 201
        assert r.get_json()["role_title"] == "New Role Routes"

    def test_create_role_missing_fields(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P1_FUTURE}/roles", json={"role_title": "No Count"})
        assert r.status_code == 400

    def test_create_role_invalid_count(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P1_FUTURE}/roles", json={
            "role_title": "Bad",
            "required_count": 0,
        })
        assert r.status_code == 400

    def test_create_role_shift_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/shifts/99999/roles", json={"role_title": "X", "required_count": 1})
        assert r.status_code == 404

    def test_create_role_volunteer_forbidden(self, client, reset_backend):
        vol = _fresh_volunteer("_src1")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shifts/{SHIFT_P1_FUTURE}/roles", json={
            "role_title": "X",
            "required_count": 1,
        })
        assert r.status_code == 403

    def test_update_shift_role(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/shift-roles/{ROLE_P1_OPEN}", json={"role_title": "Updated Role"})
        assert r.status_code == 200
        assert r.get_json()["role_title"] == "Updated Role"

    def test_update_shift_role_required_count(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/shift-roles/{ROLE_P1_OPEN}", json={"required_count": 5})
        assert r.status_code == 200

    def test_update_shift_role_invalid_count(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/shift-roles/{ROLE_P1_OPEN}", json={"required_count": 0})
        assert r.status_code == 400

    def test_update_shift_role_no_fields(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch(f"/api/shift-roles/{ROLE_P1_OPEN}", json={"bogus": "val"})
        assert r.status_code == 400

    def test_update_shift_role_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/shift-roles/99999", json={"role_title": "X"})
        assert r.status_code == 404

    def test_update_shift_role_unauthenticated(self, client, reset_backend):
        r = client.patch(f"/api/shift-roles/{ROLE_P1_OPEN}", json={"role_title": "X"})
        assert r.status_code == 401

    def test_delete_shift_role_no_signups(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.delete(f"/api/shift-roles/{ROLE_P1_OPEN}")
        assert r.status_code == 200
        assert r.get_json()["success"] is True

    def test_delete_shift_role_unauthenticated(self, client, reset_backend):
        r = client.delete(f"/api/shift-roles/{ROLE_P1_OPEN}")
        assert r.status_code == 401

    def test_delete_shift_role_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.delete("/api/shift-roles/99999")
        assert r.status_code == 404

    def test_delete_shift_role_with_signups_cancels_role(self, client, reset_backend):
        # ROLE_P4_OPEN has 1 existing signup (user 8)
        _login(client, SUPER_ADMIN_ID)
        r = client.delete(f"/api/shift-roles/{ROLE_P4_OPEN}")
        assert r.status_code == 200
        assert r.get_json()["success"] is True

    def test_create_role_on_cancelled_shift(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        client.patch(f"/api/shifts/{SHIFT_P1_FUTURE}", json={"status": "CANCELLED"})
        r = client.post(f"/api/shifts/{SHIFT_P1_FUTURE}/roles", json={
            "role_title": "X",
            "required_count": 1,
        })
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Signup routes
# ---------------------------------------------------------------------------
class TestSignupRoutes:
    def test_create_signup_success(self, client, reset_backend):
        vol = _fresh_volunteer("_s1")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup")
        assert r.status_code == 201
        data = r.get_json()
        assert data["user_id"] == vol["user_id"]
        assert data["signup_status"] == "CONFIRMED"

    def test_create_signup_unauthenticated(self, client, reset_backend):
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup")
        assert r.status_code == 401

    def test_create_signup_non_volunteer_forbidden(self, client, reset_backend):
        _login(client, LEAD_ID)
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup")
        assert r.status_code == 403

    def test_create_signup_role_not_found(self, client, reset_backend):
        vol = _fresh_volunteer("_s2")
        _login(client, vol["user_id"])
        r = client.post("/api/shift-roles/99999/signup")
        assert r.status_code == 404

    def test_create_duplicate_signup(self, client, reset_backend):
        vol = _fresh_volunteer("_s3")
        _login(client, vol["user_id"])
        client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup")
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup")
        assert r.status_code == 409

    def test_create_pending_signup(self, client, reset_backend):
        vol = _fresh_volunteer("_s4")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup", json={
            "signup_status": "PENDING_CONFIRMATION",
        })
        assert r.status_code == 201
        assert r.get_json()["signup_status"] == "PENDING_CONFIRMATION"

    def test_create_signup_for_cancelled_shift(self, client, reset_backend):
        vol = _fresh_volunteer("_s5")
        _login(client, SUPER_ADMIN_ID)
        client.patch(f"/api/shifts/{SHIFT_P4_FUTURE}", json={"status": "CANCELLED"})
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P4_OPEN}/signup")
        assert r.status_code == 400

    def test_create_signup_cannot_sign_up_for_others(self, client, reset_backend):
        vol = _fresh_volunteer("_s6")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup", json={"user_id": SUPER_ADMIN_ID})
        assert r.status_code == 403

    def test_list_signups_for_role_requires_auth(self, client, reset_backend):
        r = client.get(f"/api/shift-roles/{ROLE_P4_OPEN}/signups")
        assert r.status_code == 401

    def test_list_signups_for_role(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get(f"/api/shift-roles/{ROLE_P4_OPEN}/signups")
        assert r.status_code == 200
        signups = r.get_json()
        assert len(signups) >= 1

    def test_list_signups_role_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/shift-roles/99999/signups")
        assert r.status_code == 404

    def test_delete_signup_own(self, client, reset_backend):
        vol = _fresh_volunteer("_s7")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup")
        signup_id = r.get_json()["signup_id"]
        r2 = client.delete(f"/api/signups/{signup_id}")
        assert r2.status_code == 200

    def test_delete_signup_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.delete("/api/signups/99999")
        assert r.status_code == 404

    def test_delete_signup_others_forbidden(self, client, reset_backend):
        vol1 = _fresh_volunteer("_s8a")
        vol2 = _fresh_volunteer("_s8b")
        _login(client, vol1["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup")
        signup_id = r.get_json()["signup_id"]
        _login(client, vol2["user_id"])
        r2 = client.delete(f"/api/signups/{signup_id}")
        assert r2.status_code == 403

    def test_delete_signup_admin_can_delete_any(self, client, reset_backend):
        vol = _fresh_volunteer("_s9")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup")
        signup_id = r.get_json()["signup_id"]
        _login(client, SUPER_ADMIN_ID)
        r2 = client.delete(f"/api/signups/{signup_id}")
        assert r2.status_code == 200

    def test_delete_signup_unauthenticated(self, client, reset_backend):
        r = client.delete("/api/signups/1")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Reconfirm signup
# ---------------------------------------------------------------------------
class TestReconfirmSignup:
    def _make_pending(self, client):
        vol = _fresh_volunteer("_rcs1")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup", json={
            "signup_status": "PENDING_CONFIRMATION",
        })
        assert r.status_code == 201
        return r.get_json()["signup_id"], vol["user_id"]

    def test_reconfirm_cancel(self, client, reset_backend):
        signup_id, uid = self._make_pending(client)
        _login(client, uid)
        r = client.patch(f"/api/signups/{signup_id}/reconfirm", json={"action": "CANCEL"})
        assert r.status_code == 200
        assert r.get_json()["success"] is True

    def test_reconfirm_confirm(self, client, reset_backend):
        signup_id, uid = self._make_pending(client)
        _login(client, uid)
        r = client.patch(f"/api/signups/{signup_id}/reconfirm", json={"action": "CONFIRM"})
        assert r.status_code in (200, 409)

    def test_reconfirm_invalid_action(self, client, reset_backend):
        signup_id, uid = self._make_pending(client)
        _login(client, uid)
        r = client.patch(f"/api/signups/{signup_id}/reconfirm", json={"action": "INVALID"})
        assert r.status_code == 400

    def test_reconfirm_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/signups/99999/reconfirm", json={"action": "CONFIRM"})
        assert r.status_code == 404

    def test_reconfirm_forbidden_other_user(self, client, reset_backend):
        signup_id, _ = self._make_pending(client)
        other = _fresh_volunteer("_rcs2")
        _login(client, other["user_id"])
        r = client.patch(f"/api/signups/{signup_id}/reconfirm", json={"action": "CONFIRM"})
        assert r.status_code == 403

    def test_reconfirm_already_confirmed_returns_400(self, client, reset_backend):
        vol = _fresh_volunteer("_rcs3")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup")
        signup_id = r.get_json()["signup_id"]
        r2 = client.patch(f"/api/signups/{signup_id}/reconfirm", json={"action": "CONFIRM"})
        assert r2.status_code == 400

    def test_unauthenticated(self, client, reset_backend):
        r = client.patch("/api/signups/1/reconfirm", json={"action": "CONFIRM"})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Attendance marking
# ---------------------------------------------------------------------------
class TestAttendanceMarking:
    def test_mark_show_up_admin(self, client, reset_backend):
        vol = _fresh_volunteer("_atm1")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P4_OPEN}/signup")
        signup_id = r.get_json()["signup_id"]
        _login(client, SUPER_ADMIN_ID)
        r2 = client.patch(f"/api/signups/{signup_id}/attendance",
                           json={"attendance_status": "SHOW_UP"})
        assert r2.status_code == 200
        assert r2.get_json()["signup_status"] == "SHOW_UP"

    def test_mark_no_show_admin(self, client, reset_backend):
        vol = _fresh_volunteer("_atm2")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P4_OPEN}/signup")
        signup_id = r.get_json()["signup_id"]
        _login(client, SUPER_ADMIN_ID)
        r2 = client.patch(f"/api/signups/{signup_id}/attendance",
                           json={"attendance_status": "NO_SHOW"})
        assert r2.status_code == 200

    def test_mark_attendance_missing_field(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/signups/1/attendance", json={})
        assert r.status_code == 400

    def test_mark_attendance_unauthenticated(self, client, reset_backend):
        r = client.patch("/api/signups/1/attendance", json={"attendance_status": "SHOW_UP"})
        assert r.status_code == 401

    def test_mark_attendance_invalid_status(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/signups/1/attendance", json={"attendance_status": "INVALID"})
        assert r.status_code in (400, 403)

    def test_mark_attendance_signup_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/signups/99999/attendance",
                          json={"attendance_status": "SHOW_UP"})
        assert r.status_code == 404

    def test_volunteer_cannot_mark_attendance(self, client, reset_backend):
        vol = _fresh_volunteer("_atm3")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup")
        signup_id = r.get_json()["signup_id"]
        r2 = client.patch(f"/api/signups/{signup_id}/attendance",
                           json={"attendance_status": "SHOW_UP"})
        assert r2.status_code == 403


# ---------------------------------------------------------------------------
# Update signup (admin-only status update)
# ---------------------------------------------------------------------------
class TestUpdateSignup:
    def test_admin_update_signup_status(self, client, reset_backend):
        vol = _fresh_volunteer("_usg1")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P1_OPEN}/signup")
        signup_id = r.get_json()["signup_id"]
        _login(client, SUPER_ADMIN_ID)
        r2 = client.patch(f"/api/signups/{signup_id}", json={"signup_status": "WAITLISTED"})
        assert r2.status_code == 200

    def test_admin_update_attendance_via_update(self, client, reset_backend):
        vol = _fresh_volunteer("_usg2")
        _login(client, vol["user_id"])
        r = client.post(f"/api/shift-roles/{ROLE_P4_OPEN}/signup")
        signup_id = r.get_json()["signup_id"]
        _login(client, SUPER_ADMIN_ID)
        r2 = client.patch(f"/api/signups/{signup_id}", json={"signup_status": "NO_SHOW"})
        assert r2.status_code == 200

    def test_non_admin_forbidden(self, client, reset_backend):
        vol = _fresh_volunteer("_usg3")
        _login(client, vol["user_id"])
        r = client.patch("/api/signups/1", json={"signup_status": "CONFIRMED"})
        assert r.status_code == 403

    def test_signup_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.patch("/api/signups/99999", json={"signup_status": "CONFIRMED"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Help broadcast
# ---------------------------------------------------------------------------
class TestHelpBroadcast:
    def test_get_candidates(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast/candidates")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_get_candidates_with_query(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast/candidates?q=ben")
        assert r.status_code == 200

    def test_get_candidates_unauthenticated(self, client, reset_backend):
        r = client.get(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast/candidates")
        assert r.status_code == 401

    def test_get_candidates_shift_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.get("/api/shifts/99999/help-broadcast/candidates")
        assert r.status_code == 404

    def test_get_candidates_volunteer_forbidden(self, client, reset_backend):
        vol = _fresh_volunteer("_hb1")
        _login(client, vol["user_id"])
        r = client.get(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast/candidates")
        assert r.status_code == 403

    def test_send_broadcast_success(self, client, reset_backend):
        vol = _fresh_volunteer("_hb2")
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast", json={
            "recipient_user_ids": [vol["user_id"]],
        })
        assert r.status_code == 200
        assert "sent_count" in r.get_json()

    def test_send_broadcast_no_recipients(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast", json={
            "recipient_user_ids": [],
        })
        assert r.status_code == 400

    def test_send_broadcast_non_array(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast", json={
            "recipient_user_ids": "not_array",
        })
        assert r.status_code == 400

    def test_send_broadcast_unauthenticated(self, client, reset_backend):
        r = client.post(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast", json={
            "recipient_user_ids": [LEAD_ID],
        })
        assert r.status_code == 401

    def test_send_broadcast_not_found(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post("/api/shifts/99999/help-broadcast", json={
            "recipient_user_ids": [LEAD_ID],
        })
        assert r.status_code == 404

    def test_send_broadcast_too_many_recipients(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast", json={
            "recipient_user_ids": list(range(1, 27)),
        })
        assert r.status_code == 400

    def test_send_broadcast_invalid_user_id(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast", json={
            "recipient_user_ids": [99999],
        })
        assert r.status_code == 400

    def test_send_broadcast_non_volunteer_recipient(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast", json={
            "recipient_user_ids": [LEAD_ID],
        })
        assert r.status_code == 400

    def test_send_broadcast_non_int_recipients(self, client, reset_backend):
        _login(client, SUPER_ADMIN_ID)
        r = client.post(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast", json={
            "recipient_user_ids": ["not_int"],
        })
        assert r.status_code == 400

    def test_send_broadcast_cooldown(self, client, reset_backend):
        vol = _fresh_volunteer("_hb3")
        _login(client, SUPER_ADMIN_ID)
        client.post(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast", json={
            "recipient_user_ids": [vol["user_id"]],
        })
        r = client.post(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast", json={
            "recipient_user_ids": [vol["user_id"]],
        })
        assert r.status_code == 429

    def test_send_broadcast_cancelled_shift(self, client, reset_backend):
        vol = _fresh_volunteer("_hb4")
        _login(client, SUPER_ADMIN_ID)
        client.patch(f"/api/shifts/{SHIFT_P4_FUTURE}", json={"status": "CANCELLED"})
        r = client.post(f"/api/shifts/{SHIFT_P4_FUTURE}/help-broadcast", json={
            "recipient_user_ids": [vol["user_id"]],
        })
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------
class TestPublicRoutes:
    def test_get_public_pantries(self, client, reset_backend):
        r = client.get("/api/public/pantries")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_get_public_shifts_by_numeric_slug(self, client, reset_backend):
        r = client.get("/api/public/pantries/1/shifts")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_get_public_shifts_by_name_slug(self, client, reset_backend):
        r = client.get("/api/public/pantries/licking-county-pantry/shifts")
        assert r.status_code == 200

    def test_get_public_shifts_unknown_slug_returns_empty(self, client, reset_backend):
        r = client.get("/api/public/pantries/unknown-pantry/shifts")
        assert r.status_code == 200
        assert r.get_json() == []


# ---------------------------------------------------------------------------
# Rate limit edge cases
# ---------------------------------------------------------------------------
class TestRateLimitEdgeCases:
    def test_signup_rate_limit_triggered(self, client, reset_backend):
        vol = _fresh_volunteer("_rl1")
        _login(client, SUPER_ADMIN_ID)
        # Create 6 non-overlapping shifts so each signup doesn't trigger conflict check
        role_ids = []
        for i in range(6):
            sr = client.post(f"/api/pantries/{PANTRY_1}/shifts/full-create", json={
                "shift_name": f"RL Shift {i}",
                "start_time": f"2027-02-0{i + 1}T10:00:00Z",
                "end_time": f"2027-02-0{i + 1}T11:00:00Z",
                "roles": [{"role_title": "Helper", "required_count": 10}],
            })
            assert sr.status_code == 201
            role_ids.append(sr.get_json()["first_shift"]["roles"][0]["shift_role_id"])
        _login(client, vol["user_id"])
        for rid in role_ids[:5]:
            r = client.post(f"/api/shift-roles/{rid}/signup")
            assert r.status_code == 201
        r6 = client.post(f"/api/shift-roles/{role_ids[5]}/signup")
        assert r6.status_code == 429
