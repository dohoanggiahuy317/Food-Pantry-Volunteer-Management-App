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