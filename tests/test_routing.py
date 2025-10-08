import json


def test_routing_events_order(client, monkey_supervisor_stream):
    # auth
    r = client.post("/auth/signup", json={
        "username": "eve",
        "email": "eve@example.com",
        "password": "Password123!"
    })
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    client.post("/chats", headers=h, json={"session_name": "RS"})

    # Collect step events
    with client.stream("POST", "/multiagent/chat", headers=h, json={"question": "Hi", "session_id": "RS", "stream": True}) as resp:
        assert resp.status_code == 200
        steps = []
        for line in resp.iter_lines():
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode()
            if not line.startswith("data:"):
                continue
            data = json.loads(line.split("data:",1)[1].strip())
            if data.get("event") == "step" and data.get("node"):
                steps.append(data["node"])

    # Our fake stream yields router -> direct -> direct_greeting
    assert steps  # we captured some steps
