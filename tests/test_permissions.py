from fastapi import status


def test_session_isolation_between_users(client, monkey_supervisor_stream):
    # user A
    ra = client.post("/auth/signup", json={
        "username": "iso_a",
        "email": "iso_a@example.com",
        "password": "Password123!"
    })
    ta = ra.json()["access_token"]
    ha = {"Authorization": f"Bearer {ta}"}

    # user B
    rb = client.post("/auth/signup", json={
        "username": "iso_b",
        "email": "iso_b@example.com",
        "password": "Password123!"
    })
    tb = rb.json()["access_token"]
    hb = {"Authorization": f"Bearer {tb}"}

    # A creates session
    r = client.post("/chats", headers=ha, json={"session_name": "AS"})
    assert r.status_code == 201
    sid = r.json()["id"]

    # B cannot access A's session
    r = client.get(f"/chats/{sid}", headers=hb)
    assert r.status_code == status.HTTP_404_NOT_FOUND

    # B cannot delete A's session
    r = client.delete(f"/chats/{sid}", headers=hb)
    assert r.status_code == status.HTTP_404_NOT_FOUND
