import json
from fastapi import status


def test_streaming_multiagent_persists_and_streams(client, monkey_supervisor_stream):
    # Sign up and create session
    r = client.post("/auth/signup", json={
        "username": "bob",
        "email": "bob@example.com",
        "password": "Password123!"
    })
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # Create chat session
    r = client.post("/chats", headers=h, json={"session_name": "S1"})
    assert r.status_code == 201

    # Stream request
    payload = {"question": "Hello", "session_id": "S1", "stream": True}
    with client.stream("POST", "/multiagent/chat", headers=h, json=payload) as resp:
        assert resp.status_code == status.HTTP_200_OK
        full = ""
        for line in resp.iter_lines():
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode()
            if not line.startswith("data:"):
                continue
            data = json.loads(line.split("data:",1)[1].strip())
            if "response" in data:
                full += data["response"]
        assert "Hello" in full

    # Verify messages persisted in DB via chats endpoint
    r = client.get("/chats", headers=h)
    session = [s for s in r.json() if s["session_name"] == "S1"][0]

    r = client.get(f"/chats/{session['id']}", headers=h)
    data = r.json()
    msgs = data["messages"]
    assert len(msgs) >= 2
    assert msgs[0]["message_type"] == "user"
    assert msgs[1]["message_type"] == "agent"


def test_auto_context_injection_on_previous_chat(client, monkey_supervisor_stream):
    # Sign up and create session
    r = client.post("/auth/signup", json={
        "username": "carol",
        "email": "carol@example.com",
        "password": "Password123!"
    })
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # Create session and send two messages to build context
    client.post("/chats", headers=h, json={"session_name": "S2"})

    for q in ["First question", "Second question"]:
        with client.stream("POST", "/multiagent/chat", headers=h, json={"question": q, "session_id": "S2", "stream": True}) as resp:
            assert resp.status_code == 200
            for _ in resp.iter_lines():
                pass

    # Now, new request should preload history from DB to memory (handled server-side)
    # We simply check that messages count grows and does not error
    with client.stream("POST", "/multiagent/chat", headers=h, json={"question": "Follow up", "session_id": "S2", "stream": True}) as resp:
        assert resp.status_code == 200
        for _line in resp.iter_lines():
            pass

    # Verify we have at least 6 messages (3 turns)
    r = client.get("/chats", headers=h)
    session = [s for s in r.json() if s["session_name"] == "S2"][0]
    r = client.get(f"/chats/{session['id']}", headers=h)
    msgs = r.json()["messages"]
    # Two previous turns + current => >= 6
    assert len(msgs) >= 6
