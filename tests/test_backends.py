import sys
from pathlib import Path

# Add backend directory to Python path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

import pytest
from backends.factory import create_backend


class TestBackend:
    """Test backend storage functionality."""

    def test_backend_creation(self):
        """Test that backend can be created."""
        backend = create_backend()
        assert backend is not None

    def test_create_user(self):
        """Test creating a user."""
        backend = create_backend()
        user = backend.create_user(
            full_name="Test User",
            email="test@example.com",
            phone_number="123-456-7890",
            roles=["VOLUNTEER"]
        )
        assert user is not None
        assert user["full_name"] == "Test User"
        assert user["email"] == "test@example.com"
        assert "user_id" in user

    def test_get_user_by_id(self):
        """Test getting user by ID."""
        backend = create_backend()
        user = backend.create_user(
            full_name="Test User",
            email="test@example.com",
            phone_number="123-456-7890",
            roles=["VOLUNTEER"]
        )
        user_id = user["user_id"]

        retrieved = backend.get_user_by_id(user_id)
        assert retrieved is not None
        assert retrieved["user_id"] == user_id
        assert retrieved["full_name"] == "Test User"

    def test_get_user_by_email(self):
        """Test getting user by email."""
        backend = create_backend()
        user = backend.create_user(
            full_name="Test User",
            email="test@example.com",
            phone_number="123-456-7890",
            roles=["VOLUNTEER"]
        )

        retrieved = backend.get_user_by_email("test@example.com")
        assert retrieved is not None
        assert retrieved["email"] == "test@example.com"
        assert retrieved["full_name"] == "Test User"

    def test_update_user(self):
        """Test updating a user."""
        backend = create_backend()
        user = backend.create_user(
            full_name="Test User",
            email="test@example.com",
            phone_number="123-456-7890",
            roles=["VOLUNTEER"]
        )
        user_id = user["user_id"]

        updated = backend.update_user(user_id, {
            "full_name": "Updated Name",
            "phone_number": "987-654-3210"
        })
        assert updated is not None
        assert updated["full_name"] == "Updated Name"
        assert updated["phone_number"] == "987-654-3210"
        assert updated["email"] == "test@example.com"  # Should remain unchanged

    def test_list_roles(self):
        """Test listing available roles."""
        backend = create_backend()
        roles = backend.list_roles()
        assert isinstance(roles, list)
        assert len(roles) > 0

        # Each role should have required fields
        for role in roles:
            assert "role_id" in role
            assert "role_name" in role

    def test_get_role_by_id(self):
        """Test getting role by ID."""
        backend = create_backend()
        roles = backend.list_roles()
        if roles:
            role = backend.get_role_by_id(roles[0]["role_id"])
            assert role is not None
            assert role["role_id"] == roles[0]["role_id"]
            assert role["role_name"] == roles[0]["role_name"]


class TestBackendEdgeCases:
    """Test backend edge cases and error conditions."""

    def test_get_nonexistent_user(self):
        """Test getting a user that doesn't exist."""
        backend = create_backend()
        user = backend.get_user_by_id(99999)
        assert user is None

    def test_get_nonexistent_user_by_email(self):
        """Test getting a user by email that doesn't exist."""
        backend = create_backend()
        user = backend.get_user_by_email("nonexistent@example.com")
        assert user is None

    def test_update_nonexistent_user(self):
        """Test updating a user that doesn't exist."""
        backend = create_backend()
        updated = backend.update_user(99999, {"full_name": "New Name"})
        assert updated is None

    def test_get_role_by_invalid_id(self):
        """Test getting role by invalid ID."""
        backend = create_backend()
        role = backend.get_role_by_id(99999)
        assert role is None

    def test_create_user_duplicate_email(self):
        """Test creating user with duplicate email."""
        backend = create_backend()
        backend.create_user(
            full_name="User 1",
            email="duplicate@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )

        # This might raise an exception depending on backend implementation
        try:
            backend.create_user(
                full_name="User 2",
                email="duplicate@example.com",
                phone_number=None,
                roles=["VOLUNTEER"]
            )
            # If no exception, check that it handles duplicates gracefully
        except ValueError:
            # Expected behavior
            pass

    def test_create_and_update_user_normalizes_identity_fields(self):
        """Test email/auth fields are normalized and searchable."""
        backend = create_backend()
        user = backend.create_user(
            full_name="Identity User",
            email="  Identity@Example.COM ",
            phone_number=None,
            roles=["VOLUNTEER"],
            timezone="  America/New_York  ",
            auth_provider="  firebase  ",
            auth_uid="  uid-identity-1  ",
        )

        assert user["email"] == "identity@example.com"
        assert user["timezone"] == "America/New_York"
        assert user["auth_provider"] == "firebase"
        assert user["auth_uid"] == "uid-identity-1"
        assert backend.get_user_by_auth_uid(" uid-identity-1 ")["user_id"] == user["user_id"]
        assert backend.get_user_by_auth_uid("") is None

        updated = backend.update_user(user["user_id"], {
            "email": " NEWIdentity@Example.COM ",
            "timezone": "   ",
            "auth_provider": None,
            "auth_uid": "   ",
            "ignored": "value",
        })
        assert updated["email"] == "newidentity@example.com"
        assert updated["timezone"] is None
        assert updated["auth_provider"] is None
        assert updated["auth_uid"] is None
        assert "ignored" not in updated

    def test_update_user_rejects_duplicate_email_and_auth_uid(self):
        """Test duplicate unique identity values are rejected on update."""
        backend = create_backend()
        first = backend.create_user(
            full_name="First Identity",
            email="first-identity@example.com",
            phone_number=None,
            roles=["VOLUNTEER"],
            auth_uid="first-auth-uid",
        )
        second = backend.create_user(
            full_name="Second Identity",
            email="second-identity@example.com",
            phone_number=None,
            roles=["VOLUNTEER"],
            auth_uid="second-auth-uid",
        )

        with pytest.raises(ValueError, match="Email already exists"):
            backend.update_user(second["user_id"], {"email": first["email"].upper()})

        with pytest.raises(ValueError, match="Authentication identity already exists"):
            backend.update_user(second["user_id"], {"auth_uid": first["auth_uid"]})

    def test_replace_user_roles_filters_duplicates_and_invalid_ids(self):
        """Test replacing roles ignores duplicate/unknown roles."""
        backend = create_backend()
        user = backend.create_user(
            full_name="Role Replace User",
            email="role-replace@example.com",
            phone_number=None,
            roles=["VOLUNTEER"],
        )
        volunteer_role = backend.get_role_by_id(3)
        admin_role = backend.get_role_by_id(1)

        roles = backend.replace_user_roles(user["user_id"], [3, 1, 3, 99999])

        assert roles == [admin_role["role_name"], volunteer_role["role_name"]]
        assert backend.replace_user_roles(99999, [1]) is None


class TestPantries:
    """Test pantry operations."""

    def test_create_pantry(self):
        """Test creating a pantry."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Community Food Bank",
            location_address="123 Main St, City, State 12345",
            lead_ids=[]
        )
        assert pantry is not None
        assert pantry["name"] == "Community Food Bank"
        assert pantry["location_address"] == "123 Main St, City, State 12345"
        assert "pantry_id" in pantry
        assert "created_at" in pantry

    def test_get_pantry_by_id(self):
        """Test getting pantry by ID."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Test Pantry",
            location_address="456 Oak Ave",
            lead_ids=[]
        )
        pantry_id = pantry["pantry_id"]

        retrieved = backend.get_pantry_by_id(pantry_id)
        assert retrieved is not None
        assert retrieved["pantry_id"] == pantry_id
        assert retrieved["name"] == "Test Pantry"

    def test_get_nonexistent_pantry(self):
        """Test getting a pantry that doesn't exist."""
        backend = create_backend()
        pantry = backend.get_pantry_by_id(99999)
        assert pantry is None

    def test_list_pantries(self):
        """Test listing all pantries."""
        backend = create_backend()
        initial_count = len(backend.list_pantries())

        backend.create_pantry(
            name="Pantry 1",
            location_address="111 First St",
            lead_ids=[]
        )
        backend.create_pantry(
            name="Pantry 2",
            location_address="222 Second St",
            lead_ids=[]
        )

        pantries = backend.list_pantries()
        assert len(pantries) >= initial_count + 2

    def test_update_pantry(self):
        """Test updating a pantry."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Original Name",
            location_address="123 Main St",
            lead_ids=[]
        )
        pantry_id = pantry["pantry_id"]

        updated = backend.update_pantry(pantry_id, {
            "name": "Updated Pantry Name",
            "location_address": "456 New St"
        })
        assert updated is not None
        assert updated["name"] == "Updated Pantry Name"
        assert updated["location_address"] == "456 New St"

    def test_update_nonexistent_pantry(self):
        """Test updating a pantry that doesn't exist."""
        backend = create_backend()
        updated = backend.update_pantry(99999, {"name": "New Name"})
        assert updated is None

    def test_delete_pantry(self):
        """Test deleting a pantry."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Temp Pantry",
            location_address="789 Temp St",
            lead_ids=[]
        )
        pantry_id = pantry["pantry_id"]

        backend.delete_pantry(pantry_id)
        retrieved = backend.get_pantry_by_id(pantry_id)
        # After deletion, should not be retrievable
        assert retrieved is None

    def test_add_pantry_lead(self):
        """Test adding a lead to a pantry."""
        backend = create_backend()
        user = backend.create_user(
            full_name="Lead User",
            email="lead@example.com",
            phone_number=None,
            roles=["LEAD"]
        )
        pantry = backend.create_pantry(
            name="Lead Pantry",
            location_address="111 Lead St",
            lead_ids=[]
        )

        backend.add_pantry_lead(pantry["pantry_id"], user["user_id"])
        leads = backend.get_pantry_leads(pantry["pantry_id"])
        assert len(leads) >= 1
        lead_ids = [lead["user_id"] for lead in leads]
        assert user["user_id"] in lead_ids

    def test_remove_pantry_lead(self):
        """Test removing a lead from a pantry."""
        backend = create_backend()
        user = backend.create_user(
            full_name="Lead User",
            email="remove_lead@example.com",
            phone_number=None,
            roles=["LEAD"]
        )
        pantry = backend.create_pantry(
            name="Lead Removal Pantry",
            location_address="222 Lead Court",
            lead_ids=[user["user_id"]]
        )

        backend.remove_pantry_lead(pantry["pantry_id"], user["user_id"])
        leads = backend.get_pantry_leads(pantry["pantry_id"])
        lead_ids = [lead["user_id"] for lead in leads]
        assert user["user_id"] not in lead_ids

    def test_is_pantry_lead(self):
        """Test checking if user is pantry lead."""
        backend = create_backend()
        user = backend.create_user(
            full_name="Pantry Lead",
            email="pantry_lead@example.com",
            phone_number=None,
            roles=["LEAD"]
        )
        pantry = backend.create_pantry(
            name="Lead Check Pantry",
            location_address="333 Lead Drive",
            lead_ids=[]
        )

        # Add user as lead to pantry
        backend.add_pantry_lead(pantry["pantry_id"], user["user_id"])
        
        is_lead = backend.is_pantry_lead(pantry["pantry_id"], user["user_id"])
        assert is_lead is True

        # Create another user and check they're not a lead
        other_user = backend.create_user(
            full_name="Other User",
            email="other@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )
        is_lead = backend.is_pantry_lead(pantry["pantry_id"], other_user["user_id"])
        assert is_lead is False

    def test_create_pantry_assigns_only_valid_pantry_leads(self):
        """Test pantry creation ignores missing users and non-leads."""
        backend = create_backend()
        lead = backend.create_user(
            full_name="Valid Pantry Lead",
            email="valid-pantry-lead@example.com",
            phone_number=None,
            roles=["PANTRY_LEAD"],
        )
        volunteer = backend.create_user(
            full_name="Pantry Volunteer",
            email="pantry-volunteer@example.com",
            phone_number=None,
            roles=["VOLUNTEER"],
        )

        pantry = backend.create_pantry(
            name="Selective Lead Pantry",
            location_address="321 Selective St",
            lead_ids=[lead["user_id"], volunteer["user_id"], 99999],
        )

        assert [row["user_id"] for row in pantry["leads"]] == [lead["user_id"]]
        assert backend.is_pantry_lead(pantry["pantry_id"], lead["user_id"]) is True
        assert backend.is_pantry_lead(pantry["pantry_id"], volunteer["user_id"]) is False

    def test_pantry_subscriptions_are_idempotent_and_removable(self):
        """Test subscribe/list/unsubscribe pantry subscription helpers."""
        backend = create_backend()
        user = backend.create_user(
            full_name="Subscription User",
            email="subscription-user@example.com",
            phone_number=None,
            roles=["VOLUNTEER"],
        )
        pantry = backend.create_pantry(
            name="Subscription Pantry",
            location_address="444 Subscription Ave",
            lead_ids=[],
        )

        backend.subscribe_user_to_pantry(pantry["pantry_id"], user["user_id"])
        backend.subscribe_user_to_pantry(pantry["pantry_id"], user["user_id"])

        assert backend.list_pantry_subscriptions_for_user(user["user_id"]) == [pantry["pantry_id"]]
        assert backend.is_user_subscribed_to_pantry(pantry["pantry_id"], user["user_id"]) is True
        assert [row["user_id"] for row in backend.list_pantry_subscribers(pantry["pantry_id"])] == [user["user_id"]]

        backend.unsubscribe_user_from_pantry(pantry["pantry_id"], user["user_id"])
        assert backend.list_pantry_subscriptions_for_user(user["user_id"]) == []
        assert backend.is_user_subscribed_to_pantry(pantry["pantry_id"], user["user_id"]) is False


class TestShifts:
    """Test shift operations."""

    def test_create_shift(self):
        """Test creating a shift."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Shift Pantry",
            location_address="500 Shift St",
            lead_ids=[]
        )
        user = backend.create_user(
            full_name="Shift Creator",
            email="shift_creator@example.com",
            phone_number=None,
            roles=["LEAD"]
        )

        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Morning Shift",
            start_time="2023-05-15T08:00:00Z",
            end_time="2023-05-15T12:00:00Z",
            status="ACTIVE",
            created_by=user["user_id"]
        )
        assert shift is not None
        assert shift["shift_name"] == "Morning Shift"
        assert shift["status"] == "ACTIVE"
        assert "shift_id" in shift

    def test_get_shift_by_id(self):
        """Test getting shift by ID."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Get Shift Pantry",
            location_address="600 Get St",
            lead_ids=[]
        )
        user = backend.create_user(
            full_name="Shift User",
            email="shift_user@example.com",
            phone_number=None,
            roles=["LEAD"]
        )

        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Test Shift",
            start_time="2023-05-20T10:00:00Z",
            end_time="2023-05-20T14:00:00Z",
            status="ACTIVE",
            created_by=user["user_id"]
        )
        shift_id = shift["shift_id"]

        retrieved = backend.get_shift_by_id(shift_id)
        assert retrieved is not None
        assert retrieved["shift_id"] == shift_id
        assert retrieved["shift_name"] == "Test Shift"

    def test_get_nonexistent_shift(self):
        """Test getting a shift that doesn't exist."""
        backend = create_backend()
        shift = backend.get_shift_by_id(99999)
        assert shift is None

    def test_list_shifts_by_pantry(self):
        """Test listing shifts for a pantry."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Multi Shift Pantry",
            location_address="700 Multi St",
            lead_ids=[]
        )
        user = backend.create_user(
            full_name="Multi Shift User",
            email="multi_shift@example.com",
            phone_number=None,
            roles=["LEAD"]
        )

        backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Shift 1",
            start_time="2023-05-25T08:00:00Z",
            end_time="2023-05-25T12:00:00Z",
            status="ACTIVE",
            created_by=user["user_id"]
        )
        backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Shift 2",
            start_time="2023-05-26T13:00:00Z",
            end_time="2023-05-26T17:00:00Z",
            status="ACTIVE",
            created_by=user["user_id"]
        )

        shifts = backend.list_shifts_by_pantry(pantry["pantry_id"])
        assert len(shifts) >= 2

    def test_update_shift(self):
        """Test updating a shift."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Update Shift Pantry",
            location_address="800 Update St",
            lead_ids=[]
        )
        user = backend.create_user(
            full_name="Update User",
            email="update_user@example.com",
            phone_number=None,
            roles=["LEAD"]
        )

        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Original Shift",
            start_time="2023-06-01T08:00:00Z",
            end_time="2023-06-01T12:00:00Z",
            status="ACTIVE",
            created_by=user["user_id"]
        )
        shift_id = shift["shift_id"]

        updated = backend.update_shift(shift_id, {
            "shift_name": "Updated Shift Name",
            "status": "CANCELLED"
        })
        assert updated is not None
        assert updated["shift_name"] == "Updated Shift Name"
        assert updated["status"] == "CANCELLED"

    def test_delete_shift(self):
        """Test deleting a shift."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Delete Shift Pantry",
            location_address="900 Delete St",
            lead_ids=[]
        )
        user = backend.create_user(
            full_name="Delete User",
            email="delete_user@example.com",
            phone_number=None,
            roles=["LEAD"]
        )

        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Temp Shift",
            start_time="2023-06-10T08:00:00Z",
            end_time="2023-06-10T12:00:00Z",
            status="ACTIVE",
            created_by=user["user_id"]
        )
        shift_id = shift["shift_id"]

        backend.delete_shift(shift_id)
        retrieved = backend.get_shift_by_id(shift_id)
        assert retrieved is None

    def test_list_non_expired_shifts_in_range_filters_and_sorts(self):
        """Test range listing skips expired/cancelled shifts and sorts results."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Range Pantry",
            location_address="901 Range St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="Range Lead",
            email="range-lead@example.com",
            phone_number=None,
            roles=["PANTRY_LEAD"]
        )

        later = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Later Range Shift",
            start_time="2030-01-03T10:00:00Z",
            end_time="2030-01-03T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        earlier = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Earlier Range Shift",
            start_time="2030-01-02T10:00:00Z",
            end_time="2030-01-02T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Cancelled Range Shift",
            start_time="2030-01-02T13:00:00Z",
            end_time="2030-01-02T15:00:00Z",
            status="CANCELLED",
            created_by=lead["user_id"]
        )
        backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Expired Range Shift",
            start_time="2020-01-02T10:00:00Z",
            end_time="2020-01-02T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )

        shifts = backend.list_non_expired_shifts_in_range(
            "2030-01-01T00:00:00Z",
            "2030-01-04T00:00:00Z",
            include_cancelled=False,
        )

        assert [shift["shift_id"] for shift in shifts if shift["pantry_id"] == pantry["pantry_id"]] == [
            earlier["shift_id"],
            later["shift_id"],
        ]
        assert backend.list_non_expired_shifts_in_range("not-a-date", "2030-01-04T00:00:00Z") == []

    def test_replace_shift_and_roles_updates_creates_deletes_and_cancels(self):
        """Test replacing a shift role set handles every existing-role branch."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Replace Shift Pantry",
            location_address="902 Replace St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="Replace Shift Lead",
            email="replace-shift-lead@example.com",
            phone_number=None,
            roles=["PANTRY_LEAD"]
        )
        volunteer = backend.create_user(
            full_name="Replace Shift Volunteer",
            email="replace-shift-volunteer@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )
        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Replace Original",
            start_time="2030-02-01T10:00:00Z",
            end_time="2030-02-01T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        kept_role = backend.create_shift_role(shift["shift_id"], "Keep Me", 2)
        delete_role = backend.create_shift_role(shift["shift_id"], "Delete Me", 1)
        cancel_role = backend.create_shift_role(shift["shift_id"], "Cancel Me", 1)
        backend.create_signup(cancel_role["shift_role_id"], volunteer["user_id"], "CONFIRMED")

        updated = backend.replace_shift_and_roles(
            shift["shift_id"],
            {"shift_name": "Replace Updated", "status": "ACTIVE"},
            [
                {
                    "shift_role_id": kept_role["shift_role_id"],
                    "role_title": "Kept Updated",
                    "required_count": 3,
                },
                {"role_title": "New Role", "required_count": 4},
            ],
        )

        assert updated["shift_name"] == "Replace Updated"
        roles = {role["role_title"]: role for role in backend.list_shift_roles(shift["shift_id"])}
        assert roles["Kept Updated"]["required_count"] == 3
        assert roles["New Role"]["required_count"] == 4
        assert backend.get_shift_role_by_id(delete_role["shift_role_id"]) is None
        cancelled = backend.get_shift_role_by_id(cancel_role["shift_role_id"])
        assert cancelled["status"] == "CANCELLED"
        assert cancelled["filled_count"] == 0

    def test_replace_shift_and_roles_rejects_invalid_role_payloads(self):
        """Test role replacement validation errors."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Invalid Replace Pantry",
            location_address="903 Replace St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="Invalid Replace Lead",
            email="invalid-replace-lead@example.com",
            phone_number=None,
            roles=["PANTRY_LEAD"]
        )
        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Invalid Replace Shift",
            start_time="2030-02-02T10:00:00Z",
            end_time="2030-02-02T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        role = backend.create_shift_role(shift["shift_id"], "Existing", 1)

        with pytest.raises(ValueError, match="role_title is required"):
            backend.replace_shift_and_roles(shift["shift_id"], {}, [{"role_title": " ", "required_count": 1}])

        with pytest.raises(ValueError, match="required_count must be >= 1"):
            backend.replace_shift_and_roles(shift["shift_id"], {}, [{"role_title": "Bad Count", "required_count": 0}])

        with pytest.raises(ValueError, match="Duplicate shift_role_id"):
            backend.replace_shift_and_roles(
                shift["shift_id"],
                {},
                [
                    {"shift_role_id": role["shift_role_id"], "role_title": "One", "required_count": 1},
                    {"shift_role_id": role["shift_role_id"], "role_title": "Two", "required_count": 1},
                ],
            )

        with pytest.raises(ValueError, match="Shift role not found"):
            backend.replace_shift_and_roles(
                shift["shift_id"],
                {},
                [{"shift_role_id": 99999, "role_title": "Missing", "required_count": 1}],
            )


class TestShiftRoles:
    """Test shift role operations."""

    def test_create_shift_role(self):
        """Test creating a shift role."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Role Pantry",
            location_address="1000 Role St",
            lead_ids=[]
        )
        user = backend.create_user(
            full_name="Role User",
            email="role_user@example.com",
            phone_number=None,
            roles=["LEAD"]
        )

        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Role Shift",
            start_time="2023-07-01T08:00:00Z",
            end_time="2023-07-01T12:00:00Z",
            status="ACTIVE",
            created_by=user["user_id"]
        )

        role = backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="Food Sorter",
            required_count=3
        )
        assert role is not None
        assert role["role_title"] == "Food Sorter"
        assert role["required_count"] == 3
        assert role["filled_count"] == 0
        assert "shift_role_id" in role

    def test_list_shift_roles(self):
        """Test listing roles for a shift."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Multi Role Pantry",
            location_address="1100 Multi Role St",
            lead_ids=[]
        )
        user = backend.create_user(
            full_name="Multi Role User",
            email="multi_role@example.com",
            phone_number=None,
            roles=["LEAD"]
        )

        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Multi Role Shift",
            start_time="2023-07-10T08:00:00Z",
            end_time="2023-07-10T12:00:00Z",
            status="ACTIVE",
            created_by=user["user_id"]
        )

        backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="Cashier",
            required_count=2
        )
        backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="Packager",
            required_count=3
        )

        roles = backend.list_shift_roles(shift["shift_id"])
        assert len(roles) >= 2

    def test_get_shift_role_by_id(self):
        """Test getting shift role by ID."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Get Role Pantry",
            location_address="1200 Get Role St",
            lead_ids=[]
        )
        user = backend.create_user(
            full_name="Get Role User",
            email="get_role@example.com",
            phone_number=None,
            roles=["LEAD"]
        )

        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Get Role Shift",
            start_time="2023-07-20T08:00:00Z",
            end_time="2023-07-20T12:00:00Z",
            status="ACTIVE",
            created_by=user["user_id"]
        )

        role = backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="Test Role",
            required_count=5
        )

        retrieved = backend.get_shift_role_by_id(role["shift_role_id"])
        assert retrieved is not None
        assert retrieved["role_title"] == "Test Role"
        assert retrieved["required_count"] == 5

    def test_update_shift_role(self):
        """Test updating a shift role."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Update Role Pantry",
            location_address="1300 Update Role St",
            lead_ids=[]
        )
        user = backend.create_user(
            full_name="Update Role User",
            email="update_role@example.com",
            phone_number=None,
            roles=["LEAD"]
        )

        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Update Role Shift",
            start_time="2023-08-01T08:00:00Z",
            end_time="2023-08-01T12:00:00Z",
            status="ACTIVE",
            created_by=user["user_id"]
        )

        role = backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="Original Role",
            required_count=2
        )

        updated = backend.update_shift_role(role["shift_role_id"], {
            "role_title": "Updated Role",
            "required_count": 5
        })
        assert updated is not None
        assert updated["role_title"] == "Updated Role"
        assert updated["required_count"] == 5

    def test_delete_shift_role(self):
        """Test deleting a shift role."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Delete Role Pantry",
            location_address="1400 Delete Role St",
            lead_ids=[]
        )
        user = backend.create_user(
            full_name="Delete Role User",
            email="delete_role@example.com",
            phone_number=None,
            roles=["LEAD"]
        )

        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Delete Role Shift",
            start_time="2023-08-10T08:00:00Z",
            end_time="2023-08-10T12:00:00Z",
            status="ACTIVE",
            created_by=user["user_id"]
        )

        role = backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="Temp Role",
            required_count=1
        )

        backend.delete_shift_role(role["shift_role_id"])
        retrieved = backend.get_shift_role_by_id(role["shift_role_id"])
        assert retrieved is None


class TestSignups:
    """Test signup operations."""

    def test_create_signup(self):
        """Test creating a signup."""
        backend = create_backend()
        volunteer = backend.create_user(
            full_name="Volunteer User",
            email="volunteer@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )
        pantry = backend.create_pantry(
            name="Signup Pantry",
            location_address="1500 Signup St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="Signup Lead",
            email="signup_lead@example.com",
            phone_number=None,
            roles=["LEAD"]
        )
        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Signup Shift",
            start_time="2023-08-20T08:00:00Z",
            end_time="2023-08-20T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        shift_role = backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="Volunteer Role",
            required_count=5
        )

        signup = backend.create_signup(
            shift_role_id=shift_role["shift_role_id"],
            user_id=volunteer["user_id"],
            signup_status="CONFIRMED"
        )
        assert signup is not None
        assert signup["user_id"] == volunteer["user_id"]
        assert signup["signup_status"] == "CONFIRMED"
        assert "signup_id" in signup

    def test_list_shift_signups(self):
        """Test listing signups for a shift role."""
        backend = create_backend()
        volunteer1 = backend.create_user(
            full_name="Volunteer 1",
            email="volunteer1@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )
        volunteer2 = backend.create_user(
            full_name="Volunteer 2",
            email="volunteer2@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )
        pantry = backend.create_pantry(
            name="Multi Signup Pantry",
            location_address="1600 Multi Signup St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="Multi Signup Lead",
            email="multi_signup_lead@example.com",
            phone_number=None,
            roles=["LEAD"]
        )
        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Multi Signup Shift",
            start_time="2023-09-01T08:00:00Z",
            end_time="2023-09-01T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        shift_role = backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="Multi Volunteer Role",
            required_count=5
        )

        backend.create_signup(
            shift_role_id=shift_role["shift_role_id"],
            user_id=volunteer1["user_id"],
            signup_status="CONFIRMED"
        )
        backend.create_signup(
            shift_role_id=shift_role["shift_role_id"],
            user_id=volunteer2["user_id"],
            signup_status="CONFIRMED"
        )

        signups = backend.list_shift_signups(shift_role["shift_role_id"])
        assert len(signups) >= 2

    def test_list_signups_by_user(self):
        """Test listing signups for a user."""
        backend = create_backend()
        volunteer = backend.create_user(
            full_name="User Signups Volunteer",
            email="user_signups@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )
        pantry = backend.create_pantry(
            name="User Signups Pantry",
            location_address="1700 User Signups St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="User Signups Lead",
            email="user_signups_lead@example.com",
            phone_number=None,
            roles=["LEAD"]
        )
        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="User Signups Shift",
            start_time="2023-09-10T08:00:00Z",
            end_time="2023-09-10T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        shift_role = backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="User Signups Role",
            required_count=5
        )

        backend.create_signup(
            shift_role_id=shift_role["shift_role_id"],
            user_id=volunteer["user_id"],
            signup_status="CONFIRMED"
        )

        signups = backend.list_signups_by_user(volunteer["user_id"])
        assert len(signups) >= 1
        assert volunteer["user_id"] in [s["user_id"] for s in signups]

    def test_get_signup_by_id(self):
        """Test getting signup by ID."""
        backend = create_backend()
        volunteer = backend.create_user(
            full_name="Get Signup Volunteer",
            email="get_signup@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )
        pantry = backend.create_pantry(
            name="Get Signup Pantry",
            location_address="1800 Get Signup St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="Get Signup Lead",
            email="get_signup_lead@example.com",
            phone_number=None,
            roles=["LEAD"]
        )
        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Get Signup Shift",
            start_time="2023-09-20T08:00:00Z",
            end_time="2023-09-20T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        shift_role = backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="Get Signup Role",
            required_count=5
        )

        signup = backend.create_signup(
            shift_role_id=shift_role["shift_role_id"],
            user_id=volunteer["user_id"],
            signup_status="CONFIRMED"
        )

        retrieved = backend.get_signup_by_id(signup["signup_id"])
        assert retrieved is not None
        assert retrieved["signup_id"] == signup["signup_id"]
        assert retrieved["user_id"] == volunteer["user_id"]

    def test_update_signup(self):
        """Test updating a signup."""
        backend = create_backend()
        volunteer = backend.create_user(
            full_name="Update Signup Volunteer",
            email="update_signup@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )
        pantry = backend.create_pantry(
            name="Update Signup Pantry",
            location_address="1900 Update Signup St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="Update Signup Lead",
            email="update_signup_lead@example.com",
            phone_number=None,
            roles=["LEAD"]
        )
        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Update Signup Shift",
            start_time="2023-10-01T08:00:00Z",
            end_time="2023-10-01T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        shift_role = backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="Update Signup Role",
            required_count=5
        )

        signup = backend.create_signup(
            shift_role_id=shift_role["shift_role_id"],
            user_id=volunteer["user_id"],
            signup_status="CONFIRMED"
        )

        updated = backend.update_signup(signup["signup_id"], "NO_SHOW")
        assert updated is not None
        assert updated["signup_status"] == "NO_SHOW"

    def test_delete_signup(self):
        """Test deleting a signup."""
        backend = create_backend()
        volunteer = backend.create_user(
            full_name="Delete Signup Volunteer",
            email="delete_signup@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )
        pantry = backend.create_pantry(
            name="Delete Signup Pantry",
            location_address="2000 Delete Signup St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="Delete Signup Lead",
            email="delete_signup_lead@example.com",
            phone_number=None,
            roles=["LEAD"]
        )
        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Delete Signup Shift",
            start_time="2023-10-10T08:00:00Z",
            end_time="2023-10-10T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        shift_role = backend.create_shift_role(
            shift_id=shift["shift_id"],
            role_title="Delete Signup Role",
            required_count=5
        )

        signup = backend.create_signup(
            shift_role_id=shift_role["shift_role_id"],
            user_id=volunteer["user_id"],
            signup_status="CONFIRMED"
        )

        backend.delete_signup(signup["signup_id"])
        retrieved = backend.get_signup_by_id(signup["signup_id"])
        assert retrieved is None

    def test_pending_signup_reserves_capacity_then_expires(self):
        """Test pending signups count as occupied only until expiration."""
        backend = create_backend()
        volunteer = backend.create_user(
            full_name="Pending Volunteer",
            email="pending-volunteer@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )
        next_volunteer = backend.create_user(
            full_name="Next Pending Volunteer",
            email="next-pending-volunteer@example.com",
            phone_number=None,
            roles=["VOLUNTEER"]
        )
        pantry = backend.create_pantry(
            name="Pending Pantry",
            location_address="2100 Pending St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="Pending Lead",
            email="pending-lead@example.com",
            phone_number=None,
            roles=["PANTRY_LEAD"]
        )
        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Pending Shift",
            start_time="2030-03-01T08:00:00Z",
            end_time="2030-03-01T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        shift_role = backend.create_shift_role(shift["shift_id"], "Pending Role", 1)

        signup = backend.create_signup(shift_role["shift_role_id"], volunteer["user_id"], "PENDING_CONFIRMATION")

        assert signup["reservation_expires_at"] is not None
        assert backend.get_shift_role_by_id(shift_role["shift_role_id"])["status"] == "FULL"
        with pytest.raises(RuntimeError, match="full"):
            backend.create_signup(shift_role["shift_role_id"], next_volunteer["user_id"], "CONFIRMED")

        expired_count = backend.expire_pending_signups(shift["shift_id"], "2030-03-01T08:00:00Z")

        assert expired_count == 1
        assert backend.get_signup_by_id(signup["signup_id"])["signup_status"] == "CANCELLED"
        assert backend.get_shift_role_by_id(shift_role["shift_role_id"])["status"] == "OPEN"
        replacement = backend.create_signup(shift_role["shift_role_id"], next_volunteer["user_id"], "CONFIRMED")
        assert replacement["signup_status"] == "CONFIRMED"

    def test_bulk_mark_shift_signups_pending_skips_cancelled_and_waitlisted(self):
        """Test bulk pending conversion only affects active signup statuses."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Bulk Pending Pantry",
            location_address="2200 Pending St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="Bulk Pending Lead",
            email="bulk-pending-lead@example.com",
            phone_number=None,
            roles=["PANTRY_LEAD"]
        )
        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Bulk Pending Shift",
            start_time="2030-03-02T08:00:00Z",
            end_time="2030-03-02T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        shift_role = backend.create_shift_role(shift["shift_id"], "Bulk Pending Role", 4)
        users = [
            backend.create_user(
                full_name=f"Bulk Pending User {idx}",
                email=f"bulk-pending-user-{idx}@example.com",
                phone_number=None,
                roles=["VOLUNTEER"]
            )
            for idx in range(4)
        ]
        confirmed = backend.create_signup(shift_role["shift_role_id"], users[0]["user_id"], "CONFIRMED")
        no_show = backend.create_signup(shift_role["shift_role_id"], users[1]["user_id"], "NO_SHOW")
        cancelled = backend.create_signup(shift_role["shift_role_id"], users[2]["user_id"], "CANCELLED")
        waitlisted = backend.create_signup(shift_role["shift_role_id"], users[3]["user_id"], "WAITLISTED")

        affected = backend.bulk_mark_shift_signups_pending(shift["shift_id"], "not-a-date")

        assert {row["signup_id"] for row in affected} == {confirmed["signup_id"], no_show["signup_id"]}
        assert backend.get_signup_by_id(confirmed["signup_id"])["signup_status"] == "PENDING_CONFIRMATION"
        assert backend.get_signup_by_id(no_show["signup_id"])["reservation_expires_at"] is not None
        assert backend.get_signup_by_id(cancelled["signup_id"])["signup_status"] == "CANCELLED"
        assert backend.get_signup_by_id(waitlisted["signup_id"])["signup_status"] == "WAITLISTED"

    def test_reconfirm_pending_signup_confirms_waitlists_and_expires(self):
        """Test reconfirming pending signups covers major outcomes."""
        backend = create_backend()
        pantry = backend.create_pantry(
            name="Reconfirm Pantry",
            location_address="2300 Reconfirm St",
            lead_ids=[]
        )
        lead = backend.create_user(
            full_name="Reconfirm Lead",
            email="reconfirm-lead@example.com",
            phone_number=None,
            roles=["PANTRY_LEAD"]
        )
        shift = backend.create_shift(
            pantry_id=pantry["pantry_id"],
            shift_name="Reconfirm Shift",
            start_time="2030-03-03T08:00:00Z",
            end_time="2030-03-03T12:00:00Z",
            status="ACTIVE",
            created_by=lead["user_id"]
        )
        confirm_role = backend.create_shift_role(shift["shift_id"], "Confirm Role", 1)
        waitlist_role = backend.create_shift_role(shift["shift_id"], "Waitlist Role", 2)
        expired_role = backend.create_shift_role(shift["shift_id"], "Expired Role", 1)
        users = [
            backend.create_user(
                full_name=f"Reconfirm User {idx}",
                email=f"reconfirm-user-{idx}@example.com",
                phone_number=None,
                roles=["VOLUNTEER"]
            )
            for idx in range(4)
        ]
        confirm_signup = backend.create_signup(confirm_role["shift_role_id"], users[0]["user_id"], "PENDING_CONFIRMATION")
        backend.create_signup(waitlist_role["shift_role_id"], users[1]["user_id"], "CONFIRMED")
        waitlist_signup = backend.create_signup(waitlist_role["shift_role_id"], users[2]["user_id"], "PENDING_CONFIRMATION")
        backend.update_shift_role(waitlist_role["shift_role_id"], {"required_count": 1})
        expired_signup = backend.create_signup(expired_role["shift_role_id"], users[3]["user_id"], "PENDING_CONFIRMATION")
        backend.update_signup(expired_signup["signup_id"], "PENDING_CONFIRMATION")
        for row in backend.store["shift_signups"]:
            if row["signup_id"] == expired_signup["signup_id"]:
                row["reservation_expires_at"] = "2030-03-01T00:00:00Z"

        confirmed = backend.reconfirm_pending_signup(confirm_signup["signup_id"], "2026-05-02T00:00:00Z")
        waitlisted = backend.reconfirm_pending_signup(waitlist_signup["signup_id"], "2026-05-02T00:00:00Z")
        expired = backend.reconfirm_pending_signup(expired_signup["signup_id"], "2030-03-02T00:00:00Z")

        assert confirmed["result"] == "CONFIRMED"
        assert waitlisted["result"] == "WAITLISTED"
        assert expired["result"] == "EXPIRED"
        assert backend.reconfirm_pending_signup(99999, "2026-05-02T00:00:00Z") == {"result": "NOT_FOUND", "signup": None}
        assert backend.reconfirm_pending_signup(confirmed["signup"]["signup_id"], "2026-05-02T00:00:00Z")["result"] == "NOT_PENDING"


class TestGoogleCalendarStorage:
    """Test Google Calendar storage helpers."""

    def test_connection_upsert_preserves_refresh_token_when_missing(self):
        """Test refresh_token is not overwritten by token refresh payloads."""
        backend = create_backend()
        user = backend.create_user(
            full_name="Calendar User",
            email="calendar-user@example.com",
            phone_number=None,
            roles=["VOLUNTEER"],
        )

        created = backend.upsert_google_calendar_connection(user["user_id"], {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "calendar_id": "primary",
        })
        updated = backend.upsert_google_calendar_connection(user["user_id"], {
            "access_token": "access-2",
            "refresh_token": None,
            "calendar_id": "primary",
        })

        assert created["refresh_token"] == "refresh-1"
        assert updated["access_token"] == "access-2"
        assert updated["refresh_token"] == "refresh-1"
        assert backend.get_google_calendar_connection(user["user_id"])["access_token"] == "access-2"

        backend.delete_google_calendar_connection(user["user_id"])
        assert backend.get_google_calendar_connection(user["user_id"]) is None

    def test_event_link_upsert_and_bulk_delete(self):
        """Test event links can be upserted and removed in bulk."""
        backend = create_backend()

        first = backend.upsert_google_calendar_event_link(101, {
            "google_event_id": "event-101",
            "calendar_id": "primary",
        })
        backend.upsert_google_calendar_event_link(101, {
            "google_event_id": "event-101-updated",
            "calendar_id": "primary",
        })
        second = backend.upsert_google_calendar_event_link(102, {
            "google_event_id": "event-102",
            "calendar_id": "primary",
        })

        assert first["google_event_id"] == "event-101"
        assert backend.get_google_calendar_event_link(101)["google_event_id"] == "event-101-updated"

        backend.delete_google_calendar_event_links([101, None])
        assert backend.get_google_calendar_event_link(101) is None
        assert backend.get_google_calendar_event_link(second["signup_id"]) is not None

        backend.delete_google_calendar_event_link(second["signup_id"])
        assert backend.get_google_calendar_event_link(second["signup_id"]) is None
