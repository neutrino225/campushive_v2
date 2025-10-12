# CampusHive AI Coding Instructions

## Project Overview

CampusHive is a hierarchical multi-agent university assistant using LangGraph for orchestration, RAG for grounded answers, and FastAPI for authentication and chat persistence. The system routes questions through a supervisor to specialized agents (student info, faculty info, degree programs) with conversation memory.

## Architecture & Data Flow

### Multi-Agent Hierarchy (LangGraph)

```
User Question → Supervisor Router → Student Path    → [General RAG | Degree Advisor | Timetable]
                                  → Faculty Path    → [Faculty Agent w/ tools]
                                  → Direct Path     → [LLM w/ conversation context]
```

**Critical Files:**

- `multiagent/graph/supervisor.py` - Top-level router with async streaming
- `multiagent/nodes/student.py` - Student subgraph routing
- `multiagent/routing/classifiers.py` - LLM-based classification with keyword fallback
- `multiagent/memory/manager.py` - Thread-safe conversation memory (max 10 turns/session)

**Routing Logic:**

- Uses LLM classifiers (`classify_supervisor`, `classify_student`) with strict label validation
- Falls back to keyword heuristics on LLM failure
- Routes "direct" for greetings, thanks, follow-ups, reformatting (uses conversation context)
- Classifiers have in-memory caching to reduce API calls

### Vector Store Management (RAG)

**Central Manager:** `vector_store_manager.py`

- Three store types: `GENERAL`, `DEGREE_PROGRAMS`, `FACULTY` (enum in `VectorStoreType`)
- Hybrid retrieval: BM25 + Vector Similarity + MMR ensemble with configurable weights
- Data processors: `DegreeDataProcessor`, `FacultyDataProcessor`, `GeneralDataProcessor`
- Stores persist in `data/vector_stores/`

**Key Pattern:**

```python
# Agents instantiate retrievers via VectorStoreManager
manager = VectorStoreManager(embeddings=embeddings)
retriever = manager.get_retriever(VectorStoreType.GENERAL)
```

**Admin Commands:**

```bash
python vector_store_manager.py --action create --store-type faculty --force
python vector_store_manager.py --action info --all
```

### Authentication & Persistence (FastAPI)

**Database:** SQLite at `data/campushive.db`, SQLAlchemy ORM

- Models: `User`, `ChatSession`, `ChatMessage` (`app/database/models.py`)
- JWT auth with bcrypt passwords (`app/auth/security.py`)
- Role-based access: `student`, `faculty`, `admin`

**Critical Pattern - Chat History Loading:**

```python
# API routes load DB history into in-memory MemoryManager for LLM context
from multiagent.memory import memory_manager
await load_history_into_memory(session_id, user_id, db)
```

**Session IDs:** Can be string or int; convert to string for internal use via `get_session_id_str()`

## Code Conventions

### Error Handling - DO NOT Use Fallbacks for API Errors

**CRITICAL:** Agents re-raise API errors immediately - do NOT catch and fallback to secondary agents:

```python
# ✅ CORRECT - Re-raise API errors
try:
    answer = agent.answer(question)
except Exception as e:
    raise RuntimeError(f"Agent API error: {e}") from e

# ❌ WRONG - Don't silently fallback on API errors
try:
    answer = agent.answer(question)
except Exception:
    answer = fallback_agent.answer(question)  # No!
```

Only use fallbacks for semantic "not found" cases (e.g., `NOT_FOUND_IN_DOCUMENTS` token).

### State Management (LangGraph)

**State Classes:**

- `SupervisorState` (TypedDict): `question`, `result`, `route`, `session_id`, `conversation_history`
- `ConversationState` (Dict): Used in subgraphs
- Always pass `session_id` through state for memory tracking

**Streaming Pattern:**

```python
async def node_function(state: State, config: RunnableConfig = None) -> AsyncGenerator[State, None]:
    partial_result = ""
    for chunk in agent.stream_answer(question):
        partial_result += chunk
        yield {**state, "result": partial_result, "route": current_route + ["agent_name"]}
```

### LLM Configuration (`config.py`)

```python
llm = ChatGroq(
    model="openai/gpt-oss-120b",  # Better at strict instructions
    temperature=0.0,              # Deterministic for routing
    streaming=True
)
embeddings = OllamaEmbeddings(model="nomic-embed-text")
```

**Environment:** `.env` requires `GROQ_API_KEY`, optional `JWT_SECRET_KEY`

### Testing

**Pytest Config:** `pytest.ini` - only collects from `tests/` directory

```bash
pytest -q                          # Quick run
pytest tests/agent_tests/          # Agent-specific tests
pytest tests/api_tests/            # API/auth tests
```

**Test Structure:**

- `tests/conftest.py` - Fixtures for test DB, clients, auth tokens
- `tests/agent_tests/` - Multi-agent routing validation
- `tests/api_tests/` - FastAPI endpoint tests
- Always use test DB, never prod: `SQLALCHEMY_DATABASE_URL` in conftest overrides production

## Key Workflows

### Adding a New Agent

1. Create agent class in `multiagent/agents/` with `answer()` or `stream_answer()` method
2. Add node function in appropriate subgraph (`student.py`, `faculty.py`)
3. Update classifier in `multiagent/routing/classifiers.py` with new label
4. Add routing edge in graph builder
5. Add tests in `tests/agent_tests/`

### Rebuilding Vector Stores

```bash
# After scraping new data
python scrapers/faculty_scraper.py
python vector_store_manager.py --action create --store-type faculty --force
```

### Database Migrations

```bash
# Initialize fresh DB
python scripts/init_db.py
python scripts/create_admin.py  # Creates admin user
```

### Running the Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Access: http://localhost:8000 (chat UI)
#         http://localhost:8000/docs (API docs)
```

## Critical Gotchas

1. **Path Management:** Root directory added to `sys.path` in most files - imports from root work (e.g., `from config import llm`)
2. **Conversation Context:** Supervisor injects `conversation_context` into classifier for context-aware routing (last 3 turns)
3. **Person Resolution (Faculty):** Uses regex to extract person hints from history for pronoun follow-ups ("his email" → looks for previous person mention)
4. **NOT_FOUND_IN_DOCUMENTS Token:** Exact string returned by faculty agent when person/info not found - normalized to single token in supervisor
5. **Memory Trimming:** `MemoryManager` auto-trims to last 10 turns per session - don't store unbounded history
6. **Thread Safety:** `MemoryManager` uses `threading.RLock()` for concurrent access
7. **Async/Sync Mixing:** `run_supervisor_async()` is primary; `run_supervisor()` wraps it for CLI compatibility

## File Conventions

- Prompts: `multiagent/prompts/*.py` - plain strings, no complex templates
- Agents end in `_agent.py`, nodes in `nodes/`, graphs in `graph/`
- README docs: `README/*.md` for architecture deep-dives
- Static frontend: `app/static/index.html` served at root

## Documentation References

- Architecture: `README/Architecture.md` - routing flow, LLM classifiers, streaming
- Vector Stores: `README/README_vector_store_management.md` - retriever configs, data processing
- Memory System: `README/README_memory_system.md` - conversation tracking
- API Auth: `README/README_API_testing.md` - JWT flow, endpoints

## Environment

- FOR ANY TERMINAL BASED SESSION USE 'conda activate fyp' TO ACTIVATE THE ENVIRONMENT
