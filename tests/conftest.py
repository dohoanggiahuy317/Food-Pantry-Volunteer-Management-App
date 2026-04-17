import os
import sys
import pytest
from pathlib import Path

# Add backend directory to Python path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Set up test environment
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATA_BACKEND", "memory")
os.environ.setdefault("AUTH_PROVIDER", "memory")


@pytest.fixture(scope="session")
def setup_backend():
    """Set up the backend for testing."""
    # Import here to avoid top-level import issues
    import app
    import auth
    return app, auth


@pytest.fixture
def test_app(setup_backend):
    """Create and configure a test app instance."""
    app_module, _ = setup_backend
    app_module.app.config["TESTING"] = True
    app_module.app.config["SECRET_KEY"] = "test-secret-key"

    with app_module.app.app_context():
        yield app_module.app


@pytest.fixture
def client(test_app):
    """A test client for the app."""
    return test_app.test_client()


@pytest.fixture
def auth_service(setup_backend):
    """Create auth service for testing."""
    _, auth_module = setup_backend
    return auth_module.create_auth_service()


@pytest.fixture
def test_user(setup_backend):
    """Create a test user."""
    app_module, _ = setup_backend
    user = app_module.backend.create_user(
        full_name="Test User",
        email="test@example.com",
        phone_number="123-456-7890",
        roles=["VOLUNTEER"]
    )
    return user


@pytest.fixture
def admin_user(setup_backend):
    """Create a test admin user."""
    app_module, _ = setup_backend
    user = app_module.backend.create_user(
        full_name="Admin User",
        email="admin@example.com",
        phone_number="123-456-7890",
        roles=["ADMIN"]
    )
    return user