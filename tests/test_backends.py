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