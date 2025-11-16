# CampusHive AI Coding Agent Guide

Concise, actionable context for coding agents working on CampusHive.

## 1. System Snapshot
Hierarchical multi-agent university assistant: FastAPI backend (`app/`), LangGraph supervisor (`multiagent/graph/supervisor.py`), student & faculty subgraphs (`multiagent/nodes/`), centralized hybrid retrieval via `vector_store_manager.py`, SQLite persistence (`data/campushive.db`), session-scoped memory (`multiagent/memory/manager.py`).

## 2. Core Routing Rules
Supervisor classifier → student | faculty | direct. Student subgraph classifier → general RAG vs degree advisor. Faculty node uses structured tools. Direct path handles greetings/thanks/reformat/follow-ups. Only fallback when semantic miss (`NOT_FOUND_IN_DOCUMENTS`); NEVER fallback on API/infra errors—re-raise.

## 3. Memory & State
Always propagate `session_id` (stringify via helper) through graph state. `MemoryManager` keeps last 10 turns (thread-safe `RLock`). Conversation history injected before routing for better intent classification; agents get trimmed history for contextual answers.

## 4. Retrieval Pattern
`VectorStoreManager` provides ensemble (BM25 + embeddings + MMR) retrievers per store type: `GENERAL`, `DEGREE_PROGRAMS`, `FACULTY` (stored under `data/vector_stores/`). Use `manager.get_retriever(VectorStoreType.GENERAL)`; prefer ensemble where grounded answers matter. Rebuild with `python vector_store_manager.py --action create --store-type faculty --force`.

## 5. Key Files
`config.py` model/embeddings (keep routing deterministic). `multiagent/routing/classifiers.py` strict label validation + keyword fallback. `multiagent/graph/supervisor.py` async streaming orchestrator. `multiagent/nodes/student.py` / `faculty.py` delegate to agents. `app/database/models.py` defines `User`, `ChatSession`, `ChatMessage`. Prompts in `multiagent/prompts/` are plain strings.

## 6. Common Workflows
Env: `conda activate fyp` if Conda is still used; all installs & runs now go through `uv` for speed and reproducibility.
Dependency install/update: `uv sync` (reads `pyproject.toml` / `requirements.txt`).
Start API: `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`.
Init auth DB: `uv run python scripts/init_db.py && uv run python scripts/create_admin.py`.
Run tests: `uv run pytest -q` (scope with `tests/agent_tests/` or `tests/api_tests/`).
Rebuild stores: `uv run python scrapers/faculty_scraper.py` then `uv run python vector_store_manager.py --action create --store-type faculty --force`.
Quick supervisor probe: `uv run python -c "from multiagent.graph.supervisor import run_supervisor; print(run_supervisor('Who is the head of computer science?'))"`.
Pattern: replace bare `python/pytest/uvicorn` with `uv run <command>`; prefer `uv sync` over `pip install -r requirements.txt`.

## 7. Error Handling Conventions
Agent/tool raises → bubble up unchanged. Only semantic-not-found triggers fallback classification or alternative retrieval. Never convert operational failures into content responses. Maintain streaming behavior where implemented (async generators).

## 8. Patterns & Naming
Agents: `*_agent.py`; nodes: `multiagent/nodes/`; graph: `multiagent/graph/`; routing/helpers: `multiagent/routing/`; memory: `multiagent/memory/`. Keep imports absolute (root on `sys.path`). Session IDs may arrive as int—normalize early.

## 9. File Upload Context (If Implemented)
Uploaded file text (parsed) is appended to user question before routing; treat as ephemeral per turn, do NOT persist in long-term memory unless explicitly added.

## 10. Extensibility Guidelines
New intent → add classifier label (validate strictly), extend prompt, update keyword fallback list. New data domain → add enum in manager, processor, source directory under `data/`, rebuild store, expose via agent wrapper. Preserve deterministic routing configs when adding models.

## 11. Quick Usage Examples
Retriever: `manager = VectorStoreManager(embeddings); retriever = manager.get_retriever(VectorStoreType.FACULTY)`. Memory access: `from multiagent.memory import memory_manager; memory_manager.get_history(session_id)`. Degree queries: delegate via student node; faculty structured queries go through `FacultyAgent` tools.

## 12. Do / Avoid
Do: pass `session_id`; validate classifier labels; rebuild stores after scraper changes; use `uv sync` after dependency changes; prefix executions with `uv run`; keep prompts minimal & deterministic. Avoid: direct `pip install` / raw `python` without `uv run`; silent fallbacks on errors; expanding memory beyond 10 turns; mixing file context into persistent history; ad-hoc vector store creation outside manager.

## 13. Reference Docs
See `README/Architecture.md`, `README/README_memory_system.md`, `README/README_vector_store_management.md` for deeper details. Keep this file concise; update if workflows or routing contracts change.

Feedback: suggest missing high-impact conventions or unclear sections; keep additions concrete and codebase-backed.
