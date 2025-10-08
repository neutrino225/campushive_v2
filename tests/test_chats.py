from fastapi import status


def test_create_list_get_delete_chat_session(client):
    # Auth
    r = client.post("/auth/signup", json={
        "username": "alice",
        "email": "alice@example.com",
        "password": "Password123!"
    })
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Initially no chats
    r = client.get("/chats", headers=headers)
    assert r.status_code == 200
    assert r.json() == []

    # Create chat
    r = client.post("/chats", headers=headers, json={"session_name": "Chat 1"})
    assert r.status_code == status.HTTP_201_CREATED
    chat = r.json()

    # List shows one
    r = client.get("/chats", headers=headers)
    items = r.json()
    assert len(items) == 1
    assert items[0]["session_name"] == "Chat 1"

    # Get with messages
    r = client.get(f"/chats/{chat['id']}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["session_name"] == "Chat 1"
    assert data["messages"] == []

    # Delete
    r = client.delete(f"/chats/{chat['id']}", headers=headers)
    assert r.status_code == status.HTTP_204_NO_CONTENT

    # Not found now
    r = client.get(f"/chats/{chat['id']}", headers=headers)
    assert r.status_code == status.HTTP_404_NOT_FOUND
