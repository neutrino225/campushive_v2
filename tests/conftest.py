"""
Pytest configuration and fixtures for CampusHive tests.
"""

import os
import sys
import pytest
import asyncio
from pathlib import Path

# Add project root to path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

# Langfuse configuration
LANGFUSE_ENABLED = True
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-f554be55-d9c0-4bb6-ba78-fa7bde1a1a4a")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-e430fde3-937c-4064-b967-42218379e1b9")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

try:
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler
    
    langfuse_client = Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST
    )
    
    if langfuse_client.auth_check():
        print(f"\n✅ Langfuse connected: {LANGFUSE_HOST}")
    else:
        print(f"\n❌ Langfuse authentication failed")
        LANGFUSE_ENABLED = False
except Exception as e:
    print(f"\n⚠️  Langfuse initialization failed: {e}")
    LANGFUSE_ENABLED = False
    langfuse_client = None


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def test_session_id(request):
    """Generate unique session ID for each test."""
    import time
    module = request.node.module.__name__.split(".")[-1]
    function = request.node.name
    timestamp = int(time.time() * 1000)
    return f"{module}__{function}__{timestamp}"


@pytest.fixture(scope="function")
def langfuse_handler(request, test_session_id):
    """Provide Langfuse CallbackHandler for automatic tracing."""
    if not LANGFUSE_ENABLED:
        yield None
        return
    
    handler = None
    try:
        # SDK v3: CallbackHandler uses environment variables
        # Ensure they are set
        if LANGFUSE_SECRET_KEY:
            os.environ["LANGFUSE_SECRET_KEY"] = LANGFUSE_SECRET_KEY
        if LANGFUSE_PUBLIC_KEY:
            os.environ["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_PUBLIC_KEY
        if LANGFUSE_HOST:
            os.environ["LANGFUSE_HOST"] = LANGFUSE_HOST
            
        # Create handler with minimal config
        handler = CallbackHandler()
    except Exception as e:
        print(f"\n⚠️  Failed to create Langfuse handler: {e}")
    
    yield handler
    
    # Cleanup: flush if handler was created successfully
    if handler:
        try:
            langfuse_client.flush()
        except Exception as e:
            print(f"\n⚠️  Failed to flush Langfuse: {e}")


@pytest.fixture(scope="function")
def langfuse_config(langfuse_handler, test_session_id):
    """Provide pre-configured dict for LangChain agents."""
    if not langfuse_handler:
        return {}
    
    return {
        "callbacks": [langfuse_handler],
        "metadata": {"langfuse_session_id": test_session_id}
    }


@pytest.fixture(scope="session")
def test_db():
    """Provide test database connection."""
    from app.database.connection import get_db
    return next(get_db())


@pytest.fixture(scope="function")
def db_session(test_db):
    """Provide database session for each test."""
    yield test_db
    test_db.rollback()


@pytest.fixture(scope="module")
def test_client():
    """Provide FastAPI test client."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture(scope="function")
def test_user(db_session):
    """Create test user for authentication tests."""
    from app.database.models import User
    from app.auth.security import get_password_hash
    
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpass123"),
        is_active=True,
        is_admin=False
    )
    
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    yield user
    
    try:
        db_session.delete(user)
        db_session.commit()
    except:
        db_session.rollback()


@pytest.fixture(scope="function")
def admin_user(db_session):
    """Create admin user for authorization tests."""
    from app.database.models import User
    from app.auth.security import get_password_hash
    
    user = User(
        username="admin",
        email="admin@example.com",
        hashed_password=get_password_hash("adminpass123"),
        is_active=True,
        is_admin=True
    )
    
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    yield user
    
    try:
        db_session.delete(user)
        db_session.commit()
    except:
        db_session.rollback()


@pytest.fixture(scope="function")
def auth_token(test_client, test_user):
    """Provide authentication token for API tests."""
    response = test_client.post(
        "/auth/login",
        json={"username": "testuser", "password": "testpass123"}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    return None


@pytest.fixture(scope="function")
def auth_headers(auth_token):
    """Provide authentication headers for API tests."""
    if auth_token:
        return {"Authorization": f"Bearer {auth_token}"}
    return {}


def create_test_user(test_client):
    """Helper function to create and authenticate a test user.
    
    Returns:
        tuple: (headers, email, username, user_id) - auth headers and user info
    """
    import uuid
    
    unique_email = f"test_user_{uuid.uuid4()}@example.com"
    password = "TestPassword123"
    username = f"user_{uuid.uuid4().hex[:8]}"
    
    # Signup (returns token directly)
    signup_response = test_client.post(
        "/auth/signup",
        json={
            "username": username,
            "email": unique_email,
            "password": password
        }
    )
    
    data = signup_response.json()
    token = data["access_token"]
    user_id = data["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    
    return headers, unique_email, username, user_id


def pytest_sessionfinish(session, exitstatus):
    """Flush Langfuse at end of test session."""
    if LANGFUSE_ENABLED and langfuse_client:
        print("\n🔄 Flushing Langfuse traces...")
        langfuse_client.flush()
        print("✅ Langfuse traces sent\n")
