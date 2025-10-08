from fastapi import status


def test_multiagent_nonstream_persists_and_returns_result(client, monkey_supervisor_stream, monkey_run_supervisor_async):
    # auth
    r = client.post("/auth/signup", json={
        "username": "dave",
        "email": "dave@example.com",
        "password": "Password123!"
    })
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # create session
    client.post("/chats", headers=h, json={"session_name": "NS1"})

    # non-stream request
    r = client.post(
        "/multiagent/chat",
        headers=h,
        json={"question": "Hello non-stream", "session_id": "NS1", "stream": False},
    )
    assert r.status_code == status.HTTP_200_OK
    body = r.json()
    assert body["session_id"] == "NS1"
    assert body.get("result") is not None or body.get("response") is not None

    # verify persistence
    sessions = client.get("/chats", headers=h).json()
    sid = [s["id"] for s in sessions if s["session_name"] == "NS1"][0]
    data = client.get(f"/chats/{sid}", headers=h).json()
    msgs = data["messages"]
    assert len(msgs) >= 2
    assert msgs[-1]["message_type"] == "agent"
