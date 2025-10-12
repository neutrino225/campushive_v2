"""
Test user endpoints: user management operations.
Only tests for IMPLEMENTED features.
"""
import pytest
import uuid
from fastapi import status


def create_user_with_auth(test_client):
    """Helper function to create and authenticate a user."""
    unique_email = f"user_{uuid.uuid4()}@example.com"
    password = "TestPassword123"
    username = f"user_{uuid.uuid4().hex[:8]}"
    
    signup_response = test_client.post(
        "/auth/signup",
        json={
            "username": username,
            "email": unique_email,
            "password": password
        }
    )
    
    data = signup_response.json()
    user_id = data["user"]["id"]
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    return headers, unique_email, user_id, username


@pytest.mark.api
def test_get_current_user(test_client):
    """Test getting current authenticated user info via /auth/me."""
    headers, email, user_id, username = create_user_with_auth(test_client)
    
    response = test_client.get(
        "/auth/me",
        headers=headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["email"] == email
    assert data["id"] == user_id
    assert data["username"] == username
    assert "password" not in data


@pytest.mark.api
def test_get_current_user_without_auth(test_client):
    """Test getting current user without authentication fails."""
    response = test_client.get("/auth/me")
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.api
def test_delete_user_account(test_client):
    """Test user deletion by admin (admin only feature)."""
    # Create a regular user
    headers1, _, user_id1, _ = create_user_with_auth(test_client)
    
    # Create another user (would need admin role to delete first user)
    headers2, _, user_id2, _ = create_user_with_auth(test_client)
    
    # Try to delete first user with second user's token (should fail - not admin)
    response = test_client.delete(
        f"/admin/users/{user_id1}",
        headers=headers2
    )
    
    # Should fail because regular users can't delete other users
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.api
def test_get_user_by_id_as_admin(test_client):
    """Test getting user by ID (admin feature)."""
    headers, _, user_id, _ = create_user_with_auth(test_client)
    
    # Regular user trying to get another user's info (admin only)
    response = test_client.get(
        f"/admin/users/{user_id}",
        headers=headers
    )
    
    # Should fail - requires admin role
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.api
def test_list_all_users_as_regular_user(test_client):
    """Test that regular users cannot list all users."""
    headers, _, _, _ = create_user_with_auth(test_client)
    
    response = test_client.get(
        "/admin/users",
        headers=headers
    )
    
    # Should fail - requires admin role
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.api
def test_user_cannot_access_other_user_info(test_client):
    """Test that users cannot access other users' information."""
    # Create two users
    headers1, _, user_id1, _ = create_user_with_auth(test_client)
    headers2, _, user_id2, _ = create_user_with_auth(test_client)
    
    # User 2 tries to access User 1's info
    response = test_client.get(
        f"/admin/users/{user_id1}",
        headers=headers2
    )
    
    # Should fail - not admin
    assert response.status_code == status.HTTP_403_FORBIDDEN
