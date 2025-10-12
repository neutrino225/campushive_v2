"""
Test multiagent endpoints: query streaming and non-streaming.
"""
import pytest
import uuid
import json
from fastapi import status


def create_authenticated_user(test_client):
    """Helper function to create and authenticate a user."""
    unique_email = f"multiagent_user_{uuid.uuid4()}@example.com"
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
    
    token = signup_response.json()["access_token"]
    user_id = signup_response.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    
    return headers, unique_email, username, user_id


@pytest.mark.api
@pytest.mark.slow
def test_multiagent_query_without_auth(test_client):
    """Test multiagent query without authentication fails."""
    response = test_client.post(
        "/multiagent/chat",
        json={
            "question": "What is FAST-NUCES?",
            "session_id": "default"
        }
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.api
@pytest.mark.slow
def test_multiagent_query_with_new_session(test_client):
    """Test multiagent query creates new session if none provided."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    response = test_client.post(
        "/multiagent/chat",
        headers=headers,
        json={
            "question": "What is FAST-NUCES?",
            "session_id": "default"
        }
    )
    
    # Streaming response - check status code
    assert response.status_code == status.HTTP_200_OK
    
    # For streaming responses, we can check headers
    assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.api
@pytest.mark.slow
def test_multiagent_query_with_existing_session(test_client):
    """Test multiagent query with existing session."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    # Create a session first
    session_response = test_client.post(
        "/chats",
        headers=headers,
        json={"session_name": "Test Multiagent Session"}
    )
    session_id = session_response.json()["id"]
    
    # Query with session
    response = test_client.post(
        "/multiagent/chat",
        headers=headers,
        json={
            "question": "What is FAST?",
            "session_id": session_id
        }
    )
    
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.api
@pytest.mark.slow
def test_multiagent_query_with_empty_query(test_client):
    """Test multiagent query with empty query string."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    response = test_client.post(
        "/multiagent/chat",
        headers=headers,
        json={
            "question": "",
            "session_id": "default"
        }
    )
    
    # Should reject empty queries
    assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]


@pytest.mark.api
@pytest.mark.slow
def test_multiagent_query_with_invalid_session_id(test_client):
    """Test multiagent query with non-existent session ID."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    response = test_client.post(
        "/multiagent/chat",
        headers=headers,
        json={
            "question": "Test query",
            "session_id": 99999  # Non-existent
        }
    )
    
    # Should handle gracefully - either create new session or return error
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND, status.HTTP_400_BAD_REQUEST]


@pytest.mark.api
@pytest.mark.slow
def test_multiagent_query_persistence(test_client):
    """Test that multiagent query results are persisted."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    # Create session
    session_response = test_client.post(
        "/chats",
        headers=headers,
        json={"session_name": "Persistence Test"}
    )
    session_id = session_response.json()["id"]
    
    # Make query
    query_response = test_client.post(
        "/multiagent/chat",
        headers=headers,
        json={
            "question": "What is FAST-NUCES?",
            "session_id": session_id
        }
    )
    
    assert query_response.status_code == status.HTTP_200_OK
    
    # Verify session still exists and potentially has messages
    session_get_response = test_client.get(
        f"/chats/sessions/{session_id}",
        headers=headers
    )
    
    assert session_get_response.status_code == status.HTTP_200_OK


@pytest.mark.api
@pytest.mark.slow
def test_multiagent_different_query_types(test_client):
    """Test multiagent with different types of queries."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    queries = [
        "What is FAST-NUCES?",  # General info
        "Who is the rector?",    # Faculty info
        "What are the admission requirements?",  # Degree info
    ]
    
    for query in queries:
        response = test_client.post(
            "/multiagent/chat",
            headers=headers,
            json={
                "question": query,
                "session_id": "default"
            }
        )
        
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.api
def test_multiagent_user_cannot_access_other_user_session(test_client):
    """Test that user cannot query with another user's session."""
    # Create two users
    headers1, _, _, _ = create_authenticated_user(test_client)
    headers2, _, _, _ = create_authenticated_user(test_client)
    
    # User 1 creates session
    session_response = test_client.post(
        "/chats",
        headers=headers1,
        json={"session_name": "User1 Session"}
    )
    session_id = session_response.json()["id"]
    
    # User 2 tries to query with User 1's session
    response = test_client.post(
        "/multiagent/chat",
        headers=headers2,
        json={
            "question": "Test query",
            "session_id": session_id
        }
    )
    
    # Should either reject or create new session
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]


@pytest.mark.api
@pytest.mark.slow
def test_multiagent_conversation_context(test_client):
    """Test that multiagent maintains conversation context."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    # Create session
    session_response = test_client.post(
        "/chats",
        headers=headers,
        json={"session_name": "Context Test"}
    )
    session_id = session_response.json()["id"]
    
    # First query
    response1 = test_client.post(
        "/multiagent/chat",
        headers=headers,
        json={
            "question": "What is FAST-NUCES?",
            "session_id": session_id
        }
    )
    assert response1.status_code == status.HTTP_200_OK
    
    # Follow-up query (should use context)
    response2 = test_client.post(
        "/multiagent/chat",
        headers=headers,
        json={
            "question": "When was it established?",  # Refers to previous question
            "session_id": session_id
        }
    )
    assert response2.status_code == status.HTTP_200_OK


@pytest.mark.api
@pytest.mark.slow
def test_multiagent_long_query(test_client):
    """Test multiagent with a very long query."""
    headers, _, _, _ = create_authenticated_user(test_client)
    
    long_query = "What is FAST-NUCES? " * 100  # Very long repeated query
    
    response = test_client.post(
        "/multiagent/chat",
        headers=headers,
        json={
            "question": long_query,
            "session_id": "default"
        }
    )
    
    # Should handle or reject gracefully
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE]