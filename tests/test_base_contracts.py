from __future__ import annotations

import pytest

from auth.base import AuthService
from backends.base import StoreBackend


STORE_BACKEND_METHOD_CALLS = [
    ("get_user_by_id", (1,)),
    ("get_user_by_email", ("user@example.com",)),
    ("get_user_by_auth_uid", ("auth-uid",)),
    ("get_role_by_id", (1,)),
    ("get_user_roles", (1,)),
    ("list_users", ()),
    ("list_help_broadcast_candidates", (1,)),
    ("list_roles", ()),
    ("create_user", ("User", "user@example.com", None, ["VOLUNTEER"])),
    ("update_user", (1, {"full_name": "User"})),
    ("replace_user_roles", (1, [3])),
    ("delete_user", (1,)),
    ("list_pantries", ()),
    ("get_pantry_by_id", (1,)),
    ("get_pantry_by_slug", ("pantry",)),
    ("get_pantry_leads", (1,)),
    ("is_pantry_lead", (1, 1)),
    ("create_pantry", ("Pantry", "123 Main St", [])),
    ("update_pantry", (1, {"name": "Pantry"})),
    ("delete_pantry", (1,)),
    ("add_pantry_lead", (1, 1)),
    ("remove_pantry_lead", (1, 1)),
    ("list_pantry_subscriptions_for_user", (1,)),
    ("is_user_subscribed_to_pantry", (1, 1)),
    ("subscribe_user_to_pantry", (1, 1)),
    ("unsubscribe_user_from_pantry", (1, 1)),
    ("list_pantry_subscribers", (1,)),
    ("list_shifts_by_pantry", (1,)),
    ("list_non_expired_shifts_by_pantry", (1,)),
    ("list_non_expired_shifts_in_range", ("2030-01-01T00:00:00Z", "2030-01-02T00:00:00Z")),
    ("list_shifts_in_range", ("2030-01-01T00:00:00Z", "2030-01-02T00:00:00Z")),
    ("get_shift_by_id", (1,)),
    ("list_shifts_by_series", (1,)),
    ("get_shift_series_by_id", (1,)),
    ("create_shift_series", ({"pantry_id": 1},)),
    ("update_shift_series", (1, {"timezone": "UTC"})),
    ("create_shift", (1, "Shift", "2030-01-01T00:00:00Z", "2030-01-01T02:00:00Z", "OPEN", 1)),
    ("update_shift", (1, {"shift_name": "Shift"})),
    ("replace_shift_and_roles", (1, {"shift_name": "Shift"}, [])),
    ("delete_shift", (1,)),
    ("list_shift_roles", (1,)),
    ("get_shift_role_by_id", (1,)),
    ("create_shift_role", (1, "Role", 1)),
    ("update_shift_role", (1, {"role_title": "Role"})),
    ("delete_shift_role", (1,)),
    ("list_shift_signups", (1,)),
    ("get_latest_help_broadcast_for_sender", (1,)),
    ("create_help_broadcast", (1, 1, 1)),
    ("list_signups_by_user", (1,)),
    ("get_signup_by_id", (1,)),
    ("create_signup", (1, 1, "CONFIRMED")),
    ("delete_signup", (1,)),
    ("update_signup", (1, "CONFIRMED")),
    ("bulk_mark_shift_signups_pending", (1, "2030-01-01T00:00:00Z")),
    ("expire_pending_signups", (1, "2030-01-01T00:00:00Z")),
    ("reconfirm_pending_signup", (1, "2030-01-01T00:00:00Z")),
    ("get_google_calendar_connection", (1,)),
    ("upsert_google_calendar_connection", (1, {"access_token": "token"})),
    ("delete_google_calendar_connection", (1,)),
    ("get_google_calendar_event_link", (1,)),
    ("upsert_google_calendar_event_link", (1, {"google_event_id": "event"})),
    ("delete_google_calendar_event_link", (1,)),
    ("delete_google_calendar_event_links", ([1, 2],)),
    ("is_empty", ()),
]


@pytest.mark.parametrize(("method_name", "args"), STORE_BACKEND_METHOD_CALLS)
def test_store_backend_contract_methods_raise_not_implemented(method_name, args):
    with pytest.raises(NotImplementedError):
        getattr(StoreBackend, method_name)(object(), *args)


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("get_client_config", ()),
        ("verify_google_token", ("token",)),
        ("list_memory_accounts", ()),
        ("resolve_memory_account", ("admin",)),
        ("delete_user", ("uid",)),
    ],
)
def test_auth_service_contract_methods_raise_not_implemented(method_name, args):
    with pytest.raises(NotImplementedError):
        getattr(AuthService, method_name)(object(), *args)
