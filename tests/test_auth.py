from fastapi import status


def test_signup_and_login_flow(client):
    # Signup
    r = client.post("/auth/signup", json={
        "username": "john",
        "email": "john@example.com",
        "password": "Password123!"
    })
    assert r.status_code == status.HTTP_201_CREATED
    token = r.json()["access_token"]
    assert token

    # /auth/me with token
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == status.HTTP_200_OK
    data = r.json()
    assert data["username"] == "john"

    # Login
    r = client.post("/auth/login", json={"username": "john", "password": "Password123!"})
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["access_token"]


def test_unauthorized_access(client):
    # Without token
    r = client.get("/chats")
    # HTTPBearer without credentials yields 403 by default
    assert r.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def test_logout_endpoint(client):
    # Signup to get token
    r = client.post("/auth/signup", json={
        "username": "john2",
        "email": "john2@example.com",
        "password": "Password123!"
    })
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post("/auth/logout", headers=headers)
    assert r.status_code == status.HTTP_200_OK
    assert r.json().get("message")
