# CampusHive AI Coding Agent Instructions

## Project Overview

CampusHive is a hierarchical multi-agent university assistant. It uses LangGraph for agent orchestration, RAG for grounded answers, and FastAPI for authentication and chat persistence. The system routes user questions through a supervisor to specialized agents (student info, faculty info, degree programs), maintaining conversation memory for context.

## Architecture & Data Flow

- **Supervisor Router** (`multiagent/graph/supervisor.py`): Top-level async router, streams results, injects conversation context for routing.
- **Student/Faculty Subgraphs** (`multiagent/nodes/student.py`, `multiagent/nodes/faculty.py`): Route to specialized agents.
- **Classifiers** (`multiagent/routing/classifiers.py`): LLM-based, strict label validation, keyword fallback, in-memory cache.
- **Memory** (`multiagent/memory/manager.py`): Thread-safe, trims to last 10 turns/session.
- **Vector Store** (`vector_store_manager.py`): Hybrid BM25+Vector+MMR retrieval, three store types (`GENERAL`, `DEGREE_PROGRAMS`, `FACULTY`), persists in `data/vector_stores/`.
- **FastAPI Backend** (`app/main.py`): Handles auth, chat, and session persistence. SQLite DB at `data/campushive.db` (models in `app/database/models.py`).

**Routing:**

- LLM classifiers (`classify_supervisor`, `classify_student`) with strict label validation; fallback to keyword heuristics only on LLM failure.
- "Direct" route for greetings, thanks, follow-ups, reformatting (uses conversation context).
- Fallbacks are only for semantic "not found" (e.g., `NOT_FOUND_IN_DOCUMENTS`), never for API errors (see below).

## Key Workflows

- **Run server:**
  ```zsh
  conda activate fyp
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  # http://localhost:8000 (UI), http://localhost:8000/docs (API docs)
  ```
- **Test:**
  ```zsh
  pytest -q
  pytest tests/agent_tests/
  pytest tests/api_tests/
  ```
- **Rebuild vector stores:**
  ```zsh
  python scrapers/faculty_scraper.py
  python vector_store_manager.py --action create --store-type faculty --force
  ```
- **DB migration/init:**
  ```zsh
  python scripts/init_db.py
  python scripts/create_admin.py
  ```

## Project Conventions & Patterns

- **Error Handling:** Agents must re-raise API errors immediately; never fallback to secondary agents on API error. Only fallback for semantic "not found" (e.g., `NOT_FOUND_IN_DOCUMENTS`).
- **State:** Always pass `session_id` through state for memory tracking. Use `SupervisorState` and `ConversationState` as defined in `multiagent/graph/supervisor.py` and subgraphs.
- **Streaming:** Use async generators for streaming agent responses (see supervisor and node functions).
- **LLM Config:** See `config.py` for model/embedding setup. Use deterministic settings for routing.
- **Path Management:** Most files add root to `sys.path` for absolute imports (e.g., `from config import llm`).
- **Memory:** `MemoryManager` trims to last 10 turns/session, uses `threading.RLock()` for thread safety.
- **Session IDs:** Can be string or int; always convert to string internally (`get_session_id_str`).
- **Prompts:** Plain strings in `multiagent/prompts/*.py`.
- **File Naming:** Agents end with `_agent.py`, nodes in `nodes/`, graphs in `graph/`.

## Examples & References

- **VectorStoreManager usage:**
  ```python
  manager = VectorStoreManager(embeddings=embeddings)
  retriever = manager.get_retriever(VectorStoreType.GENERAL)
  ```
- **Chat history loading:**
  ```python
  from multiagent.memory import memory_manager
  await load_history_into_memory(session_id, user_id, db)
  ```

## Documentation

- Architecture: `README/Architecture.md`
- Vector Stores: `README/README_vector_store_management.md`
- Memory: `README/README_memory_system.md`
- API/Auth: `README/README_API_testing.md`

## Environment

- **Always**: `conda activate fyp` before running terminal-based sessions.
