import os
import sys
import json
import types
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

# Ensure project root is on sys.path so `import app` works when pytest CWD differs
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Provide light stubs for optional heavy deps used in config during import
if "langchain_ollama" not in sys.modules:
    mod = types.ModuleType("langchain_ollama")
    class _OE:
        def __init__(self, *args, **kwargs):
            pass
    mod.OllamaEmbeddings = _OE
    sys.modules["langchain_ollama"] = mod

if "langchain_groq" not in sys.modules:
    mod = types.ModuleType("langchain_groq")
    class _CG:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model")
            self.streaming = kwargs.get("streaming", True)
        def __call__(self, *a, **k):
            return {"result": "stub"}
    mod.ChatGroq = _CG
    sys.modules["langchain_groq"] = mod

# Point imports to app
"""
Create a lightweight stub for multiagent.graph.supervisor BEFORE importing app.main
so that router imports resolve to our stub rather than initializing the heavy real graph.
Do NOT override the top-level 'multiagent' package to keep other subpackages available.
"""
import types as _types, importlib
stub_sup = _types.ModuleType("multiagent.graph.supervisor")

class _StubGraph:
    async def astream_events(self, initial_state, version="v1"):
        # Default minimal event stream
        route = ["router", "direct", "direct_greeting"]
        for node in route:
            yield {"event": "on_chain_start", "name": node, "data": {}}
        # Stream three partial chunks
        for ch in ["Hello ", "from ", "agent"]:
            yield {"event": "on_chain_stream", "name": "direct", "data": {"chunk": {"result": ch, "route": route}}}
        # Final output
        yield {"event": "on_chain_end", "name": "direct", "data": {"output": {"result": "Hello from agent", "route": route}}}

async def run_supervisor_async(question: str, session_id: str):
    return {"result": f"Echo: {question}", "route": ["direct"]}

def run_supervisor(question: str, session_id: str):
    return {"result": f"Echo: {question}", "route": ["direct"]}

stub_sup.supervisor_graph = _StubGraph()
stub_sup.run_supervisor_async = run_supervisor_async
stub_sup.run_supervisor = run_supervisor

# Ensure the parent package is loaded, then override just the submodule
importlib.import_module("multiagent")
importlib.import_module("multiagent.graph")
sys.modules["multiagent.graph.supervisor"] = stub_sup

from app.main import app
from app.database.connection import Base
from app.database import get_db

# Use an in-memory SQLite DB for speed and isolation
TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()

@pytest.fixture()
def db_session(db_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def override_db_dependency(db_session):
    def _get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.clear()

@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c

# Helpers

def signup_and_login(client, username="user1", email="user1@example.com", password="Password123!"):
    # Signup
    r = client.post("/auth/signup", json={
        "username": username,
        "email": email,
        "password": password
    })
    assert r.status_code in (200, 201), r.text
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers

class FakeEventStream:
    """Yield a deterministic set of SSE-like events for testing streaming."""
    def __init__(self, result="Hello from agent", route=("router","direct","direct_greeting")):
        self.result = result
        self.route = list(route)

    async def __aiter__(self):
        # Simulate step events
        for node in self.route:
            yield {"event": "on_chain_start", "name": node, "data": {}}
        # Simulate partials
        for ch in ["Hello ", "from ", "agent"]:
            yield {"event": "on_chain_stream", "name": "direct", "data": {"chunk": {"result": ch, "route": self.route}}}
        # Final
        yield {"event": "on_chain_end", "name": "direct", "data": {"output": {"result": self.result, "route": self.route}}}

@pytest.fixture()
def monkey_supervisor_stream(monkeypatch):
    # Patch supervisor_graph.astream_events to emit our fake events
    from multiagent.graph import supervisor as sup
    async def astream_events(initial_state, version="v1"):
        async for e in FakeEventStream():
            yield e
    monkeypatch.setattr(sup.supervisor_graph, "astream_events", astream_events)
    return True

@pytest.fixture()
def monkey_run_supervisor_async(monkeypatch):
    """Patch non-streaming supervisor function to a deterministic response."""
    from multiagent.graph import supervisor as sup

    async def fake_run_supervisor_async(question: str, session_id: str):
        # Mimic the contract used by the endpoint
        return {"result": f"Echo: {question}", "route": ["direct"]}

    monkeypatch.setattr(sup, "run_supervisor_async", fake_run_supervisor_async)
    return True
