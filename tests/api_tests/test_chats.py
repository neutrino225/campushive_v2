"""
Test chat session endpoints: create, list, get, update, delete.
"""
import pytest
import uuid
from fastapi import status


def create_authenticated_user(test_client):
    """Helper function to create and authenticate a user."""
    unique_email = f"chat_user_{uuid.uuid4()}@example.com"
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
    
    token = signup_response.json()["access_token"]
    user_id = signup_response.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    
    return headers, unique_email, username, user_id


@pytest.mark.api
def test_create_chat_session(test_client):
    """Test creating a new chat session."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    response = test_client.post(
        "/chats",
        headers=headers,
        json={"session_name": "Test Chat Session"}
    )
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "id" in data
    assert data["session_name"] == "Test Chat Session"
    assert "created_at" in data


@pytest.mark.api
def test_create_chat_session_without_auth(test_client):
    """Test creating chat session without authentication fails."""
    response = test_client.post(
        "/chats",
        json={"session_name": "Test Chat"}
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.api
def test_list_chat_sessions(test_client):
    """Test listing all chat sessions for authenticated user."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    # Create multiple sessions
    for i in range(3):
        test_client.post(
            "/chats",
            headers=headers,
            json={"session_name": f"Chat Session {i}"}
        )
    
    # List sessions
    response = test_client.get(
        "/chats",
        headers=headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    
    # Verify sessions have required fields
    for session in data:
        assert "id" in session
        assert "title" in session
        assert "created_at" in session


@pytest.mark.api
def test_get_specific_chat_session(test_client):
    """Test getting a specific chat session by ID."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    # Create session
    create_response = test_client.post(
        "/chats",
        headers=headers,
        json={"session_name": "Specific Chat"}
    )
    session_id = create_response.json()["id"]
    
    # Get session
    response = test_client.get(
        f"/chats/{session_id}",
        headers=headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == session_id
    assert data["session_name"] == "Specific Chat"


@pytest.mark.api
def test_get_nonexistent_chat_session(test_client):
    """Test getting non-existent chat session returns 404."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    response = test_client.get(
        f"/chats/99999",
        headers=headers
    )
    
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.api
def test_update_chat_session(test_client):
    """Test updating a chat session title."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    # Create session
    create_response = test_client.post(
        "/chats",
        headers=headers,
        json={"session_name": "Original Title"}
    )
    session_id = create_response.json()["id"]
    
    # Update session
    response = test_client.put(
        f"/chats/{session_id}",
        headers=headers,
        json={"session_name": "Updated Title"}
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["session_name"] == "Updated Title"


@pytest.mark.api
def test_delete_chat_session(test_client):
    """Test deleting a chat session."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    # Create session
    create_response = test_client.post(
        "/chats",
        headers=headers,
        json={"session_name": "To Be Deleted"}
    )
    session_id = create_response.json()["id"]
    
    # Delete session
    response = test_client.delete(
        f"/chats/{session_id}",
        headers=headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    
    # Verify deletion
    get_response = test_client.get(
        f"/chats/{session_id}",
        headers=headers
    )
    assert get_response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.api
def test_user_can_only_see_own_sessions(test_client):
    """Test that users can only see their own chat sessions."""
    # Create two users
    headers1, _, _, _ = create_authenticated_user(test_client)
    headers2, _, _, _ = create_authenticated_user(test_client)
    
    # User 1 creates sessions
    for i in range(2):
        test_client.post(
            "/chats",
            headers=headers1,
            json={"session_name": f"User1 Session {i}"}
        )
    
    # User 2 creates sessions
    for i in range(3):
        test_client.post(
            "/chats",
            headers=headers2,
            json={"session_name": f"User2 Session {i}"}
        )
    
    # User 1 lists sessions
    response1 = test_client.get(
        "/chats",
        headers=headers1
    )
    sessions1 = response1.json()
    
    # User 2 lists sessions
    response2 = test_client.get(
        "/chats",
        headers=headers2
    )
    sessions2 = response2.json()
    
    # Verify counts
    assert len(sessions1) == 2
    assert len(sessions2) == 3
    
    # Verify titles
    titles1 = [s["session_name"] for s in sessions1]
    titles2 = [s["session_name"] for s in sessions2]
    
    assert all("User1" in title for title in titles1)
    assert all("User2" in title for title in titles2)


@pytest.mark.api
def test_user_cannot_access_other_user_session(test_client):
    """Test that user cannot access another user's session."""
    # Create two users
    headers1, _, _, _ = create_authenticated_user(test_client)
    headers2, _, _, _ = create_authenticated_user(test_client)
    
    # User 1 creates session
    create_response = test_client.post(
        "/chats",
        headers=headers1,
        json={"session_name": "User1 Private Session"}
    )
    session_id = create_response.json()["id"]
    
    # User 2 tries to access User 1's session
    response = test_client.get(
        f"/chats/{session_id}",
        headers=headers2
    )
    
    # Should return 404 or 403
    assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN]


@pytest.mark.api
def test_user_cannot_delete_other_user_session(test_client):
    """Test that user cannot delete another user's session."""
    # Create two users
    headers1, _, _, _ = create_authenticated_user(test_client)
    headers2, _, _, _ = create_authenticated_user(test_client)
    
    # User 1 creates session
    create_response = test_client.post(
        "/chats",
        headers=headers1,
        json={"session_name": "User1 Session"}
    )
    session_id = create_response.json()["id"]
    
    # User 2 tries to delete User 1's session
    response = test_client.delete(
        f"/chats/{session_id}",
        headers=headers2
    )
    
    # Should return 404 or 403
    assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN]
    
    # Verify session still exists for User 1
    get_response = test_client.get(
        f"/chats/{session_id}",
        headers=headers1
    )
    assert get_response.status_code == status.HTTP_200_OK


@pytest.mark.api
def test_create_session_with_empty_title(test_client):
    """Test creating session with empty title."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    response = test_client.post(
        "/chats",
        headers=headers,
        json={"session_name": ""}
    )
    
    # Should either accept empty title or reject
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]


@pytest.mark.api
def test_create_session_with_no_title(test_client):
    """Test creating session without title field."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    response = test_client.post(
        "/chats",
        headers=headers,
        json={}
    )
    
    # Should either use default title or reject
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_422_UNPROCESSABLE_ENTITY]
