from __future__ import annotations

import importlib
import os
import sys
import types
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ["DATA_BACKEND"] = "memory"
os.environ["AUTH_PROVIDER"] = "memory"

try:
    import flask_cors  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    flask_cors_stub = types.ModuleType("flask_cors")
    flask_cors_stub.CORS = lambda *args, **kwargs: None
    sys.modules["flask_cors"] = flask_cors_stub

import app as app_module


class AdminUserManagementTestCase(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["DATA_BACKEND"] = "memory"
        os.environ["AUTH_PROVIDER"] = "memory"
        self.app_module = importlib.reload(app_module)
        self.app_module.app.config["TESTING"] = True
        self.client = self.app_module.app.test_client()
        self.backend = self.app_module.backend

        self.super_admin = self.backend.get_user_by_id(1)
        self.normal_admin = self.backend.create_user(
            full_name="Normal Admin",
            email="normal-admin@example.com",
            phone_number="555-111-0000",
            roles=["ADMIN"],
        )
        self.other_admin = self.backend.create_user(
            full_name="Other Admin",
            email="other-admin@example.com",
            phone_number="555-111-0001",
            roles=["ADMIN"],
        )
        self.target_user = self.backend.create_user(
            full_name="Target Volunteer",
            email="target-volunteer@example.com",
            phone_number="555-111-0002",
            roles=["VOLUNTEER"],
        )
        self.role_ids = {
            role["role_name"]: int(role["role_id"])
            for role in self.backend.list_roles()
        }

    def login_as(self, user_id: int) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = user_id

    def test_super_admin_can_access_user_listing(self) -> None:
        self.login_as(int(self.super_admin["user_id"]))
        response = self.client.get("/api/users")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(any("SUPER_ADMIN" in row.get("roles", []) for row in payload))

    def test_non_admin_cannot_access_user_listing(self) -> None:
        self.login_as(int(self.target_user["user_id"]))
        response = self.client.get("/api/users")
        self.assertEqual(response.status_code, 403)

    def test_user_listing_supports_search_and_role_filter(self) -> None:
        self.login_as(int(self.super_admin["user_id"]))

        search_response = self.client.get("/api/users?q=target-volunteer")
        self.assertEqual(search_response.status_code, 200)
        search_payload = search_response.get_json()
        self.assertEqual(len(search_payload), 1)
        self.assertEqual(search_payload[0]["email"], "target-volunteer@example.com")

        filter_response = self.client.get("/api/users?role=VOLUNTEER")
        self.assertEqual(filter_response.status_code, 200)
        filter_payload = filter_response.get_json()
        self.assertTrue(all("VOLUNTEER" in row.get("roles", []) for row in filter_payload))

    def test_admin_can_view_single_user_profile(self) -> None:
        self.login_as(int(self.normal_admin["user_id"]))
        response = self.client.get(f"/api/users/{int(self.target_user['user_id'])}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["email"], "target-volunteer@example.com")
        self.assertIn("VOLUNTEER", payload["roles"])

    def test_normal_admin_can_grant_admin_role(self) -> None:
        self.login_as(int(self.normal_admin["user_id"]))
        response = self.client.patch(
            f"/api/users/{int(self.target_user['user_id'])}/roles",
            json={"role_ids": [self.role_ids["ADMIN"]]},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("ADMIN", payload["roles"])

    def test_normal_admin_cannot_remove_admin_from_another_admin(self) -> None:
        self.login_as(int(self.normal_admin["user_id"]))
        response = self.client.patch(
            f"/api/users/{int(self.other_admin['user_id'])}/roles",
            json={"role_ids": [self.role_ids["VOLUNTEER"]]},
        )
        self.assertEqual(response.status_code, 403)

    def test_normal_admin_can_remove_own_admin_role(self) -> None:
        self.login_as(int(self.normal_admin["user_id"]))
        response = self.client.patch(
            f"/api/users/{int(self.normal_admin['user_id'])}/roles",
            json={"role_ids": [self.role_ids["VOLUNTEER"]]},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertNotIn("ADMIN", payload["roles"])
        self.assertEqual(payload["roles"], ["VOLUNTEER"])

        follow_up = self.client.get("/api/users")
        self.assertEqual(follow_up.status_code, 403)

    def test_super_admin_can_remove_admin_from_other_admin(self) -> None:
        self.login_as(int(self.super_admin["user_id"]))
        response = self.client.patch(
            f"/api/users/{int(self.other_admin['user_id'])}/roles",
            json={"role_ids": [self.role_ids["VOLUNTEER"]]},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertNotIn("ADMIN", payload["roles"])

    def test_role_update_rejects_multiple_roles(self) -> None:
        self.login_as(int(self.super_admin["user_id"]))
        response = self.client.patch(
            f"/api/users/{int(self.target_user['user_id'])}/roles",
            json={"role_ids": [self.role_ids["VOLUNTEER"], self.role_ids["ADMIN"]]},
        )
        self.assertEqual(response.status_code, 400)

    def test_super_admin_role_cannot_be_assigned_or_edited(self) -> None:
        self.login_as(int(self.super_admin["user_id"]))
        assign_response = self.client.patch(
            f"/api/users/{int(self.target_user['user_id'])}/roles",
            json={"role_ids": [self.role_ids["SUPER_ADMIN"]]},
        )
        self.assertEqual(assign_response.status_code, 403)

        protected_response = self.client.patch(
            f"/api/users/{int(self.super_admin['user_id'])}/roles",
            json={"role_ids": [self.role_ids["VOLUNTEER"]]},
        )
        self.assertEqual(protected_response.status_code, 403)

    def test_protected_super_admin_cannot_self_delete(self) -> None:
        self.login_as(int(self.super_admin["user_id"]))
        response = self.client.delete("/api/me", json={})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
