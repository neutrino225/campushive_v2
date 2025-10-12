"""
Test admin endpoints: vector store management and system operations.
"""
import pytest
import uuid
from fastapi import status


def create_admin_user(test_client):
    """Helper function to create an admin user and get auth token."""
    # Note: Regular signup creates 'student' role. Admin tests will be skipped.
    unique_email = f"admin_{uuid.uuid4()}@example.com"
    password = "AdminPassword123"
    username = f"admin_{uuid.uuid4().hex[:8]}"
    
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
    
    return headers, unique_email, user_id


def create_regular_user(test_client):
    """Helper function to create a regular user."""
    unique_email = f"user_{uuid.uuid4()}@example.com"
    password = "UserPassword123"
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
    
    return headers, unique_email, user_id


@pytest.mark.api
@pytest.mark.admin
def test_admin_vector_stores_list_without_auth(test_client):
    """Test listing vector stores without authentication fails."""
    response = test_client.get("/admin/vector-stores")
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.api
@pytest.mark.admin
def test_admin_vector_stores_list_with_regular_user(test_client):
    """Test that regular users cannot access admin endpoints."""
    headers, _, _ = create_regular_user(test_client)
    
    response = test_client.get(
        "/admin/vector-stores",
        headers=headers
    )
    
    # Should be forbidden for non-admin users
    assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED]


@pytest.mark.api
@pytest.mark.admin
@pytest.mark.skip(reason="Requires admin user creation mechanism")
def test_admin_vector_stores_list_with_admin(test_client):
    """Test admin can list vector stores."""
    headers, _, _ = create_admin_user(test_client)
    
    response = test_client.get(
        "/admin/vector-stores",
        headers=headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.api
@pytest.mark.admin
@pytest.mark.skip(reason="Requires admin user creation mechanism")
def test_admin_rebuild_vector_store(test_client):
    """Test admin can rebuild a vector store."""
    headers, _, _ = create_admin_user(test_client)
    
    response = test_client.post(
        "/admin/vector-stores/general/rebuild",
        headers=headers
    )
    
    # Should accept request (may return 202 for async operation)
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_202_ACCEPTED]


@pytest.mark.api
@pytest.mark.admin
def test_admin_rebuild_vector_store_without_auth(test_client):
    """Test rebuilding vector store without auth fails."""
    response = test_client.post(
        "/admin/vector-stores/general/rebuild"
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.api
@pytest.mark.admin
def test_admin_rebuild_nonexistent_vector_store(test_client):
    """Test rebuilding non-existent vector store."""
    headers, _, _ = create_regular_user(test_client)
    
    response = test_client.post(
        "/admin/vector-stores/nonexistent/rebuild",
        headers=headers
    )
    
    # Should return error (403 for non-admin or 404 for not found)
    assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND, status.HTTP_401_UNAUTHORIZED]


@pytest.mark.api
@pytest.mark.admin
@pytest.mark.skip(reason="Requires admin user creation mechanism")
def test_admin_get_vector_store_stats(test_client):
    """Test admin can get vector store statistics."""
    headers, _, _ = create_admin_user(test_client)
    
    response = test_client.get(
        "/admin/vector-stores/general/stats",
        headers=headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "document_count" in data or "stats" in data


@pytest.mark.api
@pytest.mark.admin
@pytest.mark.skip(reason="Requires admin user creation mechanism")
def test_admin_clear_vector_store(test_client):
    """Test admin can clear a vector store."""
    headers, _, _ = create_admin_user(test_client)
    
    response = test_client.delete(
        "/admin/vector-stores/general",
        headers=headers
    )
    
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.api
@pytest.mark.admin
def test_regular_user_cannot_clear_vector_store(test_client):
    """Test regular user cannot clear vector stores."""
    headers, _, _ = create_regular_user(test_client)
    
    response = test_client.delete(
        "/admin/vector-stores/general",
        headers=headers
    )
    
    assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED]


@pytest.mark.api
@pytest.mark.admin
@pytest.mark.skip(reason="Requires admin user creation mechanism and file upload")
def test_admin_upload_documents(test_client):
    """Test admin can upload documents to vector store."""
    headers, _, _ = create_admin_user(test_client)
    
    # Create a dummy file
    files = {
        "file": ("test.txt", b"Test document content", "text/plain")
    }
    
    response = test_client.post(
        "/admin/vector-stores/general/documents",
        headers=headers,
        files=files
    )
    
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]