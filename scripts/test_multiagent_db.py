#!/usr/bin/env python3
"""
Integration test for multiagent chat persistence to the SQLite DB.

This test will:
- Signup a test user
- Create a new chat session via /chats
- Call the non-streaming /multiagent/chat endpoint to create a turn
- Verify that a ChatSession and ChatMessages were persisted via /chats/{id}

Run with the `fyp` conda env active:

```bash
conda activate fyp
python scripts/test_multiagent_db.py
```
"""

import requests
import json
import time
from typing import Optional
import os
import tempfile
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import application pieces
from app.main import app
from app.database import Base, get_db
from app.database.models import User

# We'll monkeypatch the supervisor run to return a deterministic result

TEST_DB_URL = "sqlite:///{path}"


@pytest.fixture(scope="function")
def temp_db(tmp_path, monkeypatch):
    """Create a temporary SQLite database and override the app get_db dependency."""
    db_file = tmp_path / "test_db.sqlite"
    db_url = TEST_DB_URL.format(path=db_file)

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create tables
    Base.metadata.create_all(bind=engine)

    def _get_test_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr('app.routers.multiagent.get_db', _get_test_db)

    # Provide test client and DB URL for tests
    yield {"engine": engine, "db_url": db_url, "session_local": TestingSessionLocal}


@pytest.fixture()
def client(temp_db, monkeypatch):
    """Provide a TestClient with the app dependency overrides in place."""
    # Monkeypatch auth to allow creating a real user via the auth endpoints
    with TestClient(app) as c:
        yield c


def create_and_login_user(client: TestClient, username: str = "testuser", email: str = "test@example.com", password: str = "Password123!"):
    # Signup
    resp = client.post("/auth/signup", json={"username": username, "email": email, "password": password})
    assert resp.status_code == 201
    data = resp.json()
    token = data["access_token"]
    user = data["user"]
    return token, user


def test_multiagent_persists_turns(temp_db, client, monkeypatch):
    """End-to-end integration test: signup, create session, call non-streaming multiagent, assert persistence."""
    # Create and login user
    token, user = create_and_login_user(client)

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Create chat session
    resp = client.post("/chats", json={"session_name": "integration_session"}, headers=headers)
    assert resp.status_code == 201
    session = resp.json()
    session_id = session["id"]

    # Monkeypatch supervisor async run to return deterministic result
    async def fake_run_supervisor_async(question, session_name):
        return {"result": "This is a fake answer.", "route": ["direct"], "score": 1.0}

    monkeypatch.setattr('multiagent.graph.supervisor.run_supervisor_async', fake_run_supervisor_async)

    # Call non-streaming multiagent endpoint
    ma_resp = client.post("/multiagent/chat", json={"question": "Who leads CS?", "session_id": session.get("session_name"), "stream": False}, headers=headers)
    assert ma_resp.status_code == 200
    ma_data = ma_resp.json()
    assert ma_data.get("result") == "This is a fake answer."

    # Retrieve the persisted session and messages
    get_resp = client.get(f"/chats/{session_id}", headers=headers)
    assert get_resp.status_code == 200
    persisted = get_resp.json()

    messages = persisted.get("messages", [])
    # Expect at least one user and one agent message
    assert any(m["message_type"] == "user" for m in messages), "No user message persisted"
    assert any(m["message_type"] == "agent" for m in messages), "No agent message persisted"

    # Check agent message includes our fake answer
    agent_msgs = [m for m in messages if m["message_type"] == "agent"]
    assert any("fake answer" in m["content"] for m in agent_msgs)
