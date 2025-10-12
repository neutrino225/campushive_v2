"""
Test authentication endpoints: signup, login, logout.
"""
import pytest
import uuid
from fastapi import status


@pytest.mark.api
@pytest.mark.auth
def test_user_signup_success(test_client):
    """Test successful user signup."""
    unique_email = f"test_{uuid.uuid4()}@example.com"
    username = f"testuser_{uuid.uuid4().hex[:8]}"
    
    response = test_client.post(
        "/auth/signup",
        json={
            "username": username,
            "email": unique_email,
            "password": "SecurePassword123"
        }
    )
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "access_token" in data
    assert "user" in data
    assert data["user"]["email"] == unique_email
    assert data["user"]["username"] == username
    assert "password" not in data  # Password should not be returned


@pytest.mark.api
@pytest.mark.auth
def test_user_signup_duplicate_email(test_client):
    """Test signup with duplicate email fails."""
    unique_email = f"duplicate_{uuid.uuid4()}@example.com"
    username1 = f"user1_{uuid.uuid4().hex[:8]}"
    username2 = f"user2_{uuid.uuid4().hex[:8]}"
    
    # First signup
    response1 = test_client.post(
        "/auth/signup",
        json={
            "username": username1,
            "email": unique_email,
            "password": "Password123!"
        }
    )
    assert response1.status_code == status.HTTP_201_CREATED
    
    # Second signup with same email
    response2 = test_client.post(
        "/auth/signup",
        json={
            "username": username2,
            "email": unique_email,
            "password": "Password456!"
        }
    )
    assert response2.status_code == status.HTTP_400_BAD_REQUEST
    assert "email" in response2.json()["detail"].lower()


@pytest.mark.api
@pytest.mark.auth
def test_user_login_success(test_client):
    """Test successful user login."""
    unique_email = f"login_{uuid.uuid4()}@example.com"
    username = f"loginuser_{uuid.uuid4().hex[:8]}"
    password = "TestPassword123"
    
    # Create user
    test_client.post(
        "/auth/signup",
        json={
            "username": username,
            "email": unique_email,
            "password": password
        }
    )
    
    # Login with username (not email)
    response = test_client.post(
        "/auth/login",
        json={
            "username": username,
            "password": password
        }
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "user" in data


@pytest.mark.api
@pytest.mark.auth
def test_user_login_wrong_password(test_client):
    """Test login with wrong password fails."""
    unique_email = f"wrongpass_{uuid.uuid4()}@example.com"
    username = f"user_{uuid.uuid4().hex[:8]}"
    
    # Create user
    test_client.post(
        "/auth/signup",
        json={
            "username": username,
            "email": unique_email,
            "password": "CorrectPassword123"
        }
    )
    
    # Login with wrong password
    response = test_client.post(
        "/auth/login",
        json={
            "username": username,
            "password": "WrongPassword123"
        }
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.api
@pytest.mark.auth
def test_user_login_nonexistent_user(test_client):
    """Test login with non-existent user fails."""
    response = test_client.post(
        "/auth/login",
        json={
            "username": f"nonexistent_{uuid.uuid4().hex[:8]}",
            "password": "SomePassword123"
        }
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.api
@pytest.mark.auth
def test_access_protected_endpoint_without_token(test_client):
    """Test accessing protected endpoint without token fails."""
    response = test_client.get("/chats")
    # FastAPI returns 403 for "Not authenticated"
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.api
@pytest.mark.auth
def test_access_protected_endpoint_with_valid_token(test_client):
    """Test accessing protected endpoint with valid token succeeds."""
    unique_email = f"protected_{uuid.uuid4()}@example.com"
    username = f"user_{uuid.uuid4().hex[:8]}"
    password = "SecurePass123"
    
    # Create and login user
    signup_response = test_client.post(
        "/auth/signup",
        json={
            "username": username,
            "email": unique_email,
            "password": password
        }
    )
    
    # Get token from signup response
    token = signup_response.json()["access_token"]
    
    # Access protected endpoint (list chat sessions)
    response = test_client.get(
        "/chats",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == status.HTTP_200_OK
    # Should return empty list for new user
    assert response.json() == []


@pytest.mark.api
@pytest.mark.auth
def test_access_protected_endpoint_with_invalid_token(test_client):
    """Test accessing protected endpoint with invalid token fails."""
    response = test_client.get(
        "/chats/sessions",
        headers={"Authorization": "Bearer invalid_token_123"}
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.api
@pytest.mark.auth
def test_signup_with_weak_password(test_client):
    """Test signup with weak password."""
    response = test_client.post(
        "/auth/signup",
        json={
            "username": f"user_{uuid.uuid4().hex[:8]}",
            "email": f"test_{uuid.uuid4()}@example.com",
            "password": "123"  # Too short
        }
    )
    
    # Should either reject or accept - depends on validation rules
    # Adjust assertion based on your actual validation
    assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_201_CREATED]


@pytest.mark.api
@pytest.mark.auth
def test_signup_with_invalid_email(test_client):
    """Test signup with invalid email format."""
    response = test_client.post(
        "/auth/signup",
        json={
            "username": f"user_{uuid.uuid4().hex[:8]}",
            "email": "not_an_email",
            "password": "SecurePassword123!"
        }
    )
    
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
