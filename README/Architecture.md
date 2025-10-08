# Multi‑Agent Architecture (Current State, Recommendations, and Plan)

This document explains the current multi‑agent architecture in this repository, how the pieces fit together, and concrete next steps to evolve it. It’s written to be practical and implementation‑driven.

## High‑Level Overview

Goal: Provide a hierarchical assistant with a top‑level supervisor that routes queries to mid‑level domains (student vs faculty), which in turn delegate to specialized sub‑agents (general university RAG, degree advisor, faculty information).

Core technologies:

- Orchestration: LangGraph StateGraph
- LLM + embeddings: configured in `config.py` (Groq Chat model; Ollama embeddings)
- Retrieval: Central `VectorStoreManager` with Chroma stores for `GENERAL`, `DEGREE_PROGRAMS`, and `FACULTY`, plus BM25 and MMR ensemble
- Agents: `RAGEngine` (general), `DegreeAdvisorAgent`, `FacultyAgent`
- Routing: LLM‑based classifiers with keyword fallback in `multiagent/routing/classifiers.py` (in‑memory cache)
- Tests: `pytest` integration tests for routing and agent behavior

## Repository Layout (multi‑agent)

- `multiagent/graph/supervisor.py`
  - Top‑level supervisor graph with an LLM‑based router and nodes for `student`, `faculty`, and `direct` replies
  - Helper `run_supervisor(question: str) -> str` for easy invocation in tests/CLI
- `multiagent/nodes/student.py`
  - Student subgraph: LLM‑routed → `general` (RAGEngine) or `degree` (DegreeAdvisorAgent)
  - Helper `run_student(question: str) -> str` for deterministic routing in tests
- `multiagent/nodes/faculty.py`
  - Thin graph wrapper around `FacultyAgent`, used by the supervisor via `run_faculty` (minimal, single‑node for now)
- `multiagent/prompts/*.py`
  - Simple prompt snippets used by nodes/agents
- `multiagent/tests/test_supervisor.py`
  - Integration tests for supervisor routing (greeting, faculty email, student general, student degree)
- `multiagent/tests/test_routing_llm.py`
  - Unit tests validating deterministic LLM router behavior via mocking

Related single‑agent modules used by nodes:

- `general_agent.py` → `RAGEngine`
- `degree_advisor_agent.py` → `DegreeAdvisorAgent`
- `faculty_agent.py` → `FacultyAgent` (structured tools + semantic fallback, multi‑person support)
- `vector_store_manager.py` → Centralized retrievers and data processing for Chroma stores
- `config.py` → LLM and embeddings

## Current Data Flow

Given a user question:

1. `run_supervisor(question)` streams the supervisor graph.
2. Router categorizes the query:
   - Uses an LLM‑based classifier (`classify_supervisor`) with strict label parsing and keyword fallback.
   - Greetings/thanks → `direct` node returns a canned response.
   - Faculty intent → `faculty` path.
   - Otherwise → `student` path.
3. Student path:
   - `student.router` uses an LLM classifier (`classify_student`). If `degree` → call `DegreeAdvisorAgent.invoke`. Else → `RAGEngine.answer`.
   - Both nodes include fallbacks to ensure non‑empty outputs even if retrieval or LLM fails.
4. Faculty path (current):
   - Supervisor calls `run_faculty(question)` which uses a minimal faculty subgraph that wraps `FacultyAgent` (single `faculty_info` node). If needed, it can fall back to streaming `faculty_router_node` to aggregate a result.
5. Supervisor aggregates the latest `result` seen in the streamed states; if nothing is produced, it returns a helpful fallback based on detected intent.

## Error Handling and Fallbacks

- Student and supervisor nodes catch exceptions and produce deterministic, non‑empty responses.
- The supervisor adds tailored fallbacks (greeting vs degree vs general) when no node yields a result.
- `FacultyAgent` internally handles multi‑person queries, structured field tool calls (email, department, publications, etc.), and semantic fallback for summaries.
- Routers validate LLM outputs against allowed labels; if invalid or on error, they fall back to keyword heuristics.

## Streaming vs Non‑Streaming

- For reliable tests, the nodes use non‑streaming LLM calls and aggregate results. The supervisor still streams the graph, but we track the latest `result` value and return it.
- `FacultyAgent`, `RAGEngine`, and `DegreeAdvisorAgent` can stream when used interactively (outside tests).

## Testing Coverage (Current)

- Single‑agent tests validate `FacultyAgent`, `RAGEngine` (general), and `DegreeAdvisorAgent` behavior.
- Multi‑agent tests validate supervisor routing for greeting, faculty email, student general, and student degree scenarios.
- All current tests pass.
- The router unit tests (`test_routing_llm.py`) verify the LLM classifiers produce the expected labels deterministically under mocking.

## Known Limitations

- Routing is LLM‑based with keyword fallback. While more flexible, it still needs evaluation/guardrails for mixed intents and edge cases.
- Faculty subgraph is minimal (single `faculty_info` node). There’s no intent router inside the faculty path yet (e.g., email vs department vs profile).
- No persistent memory/checkpointing between turns yet (LangGraph supports this; not wired).
- No unified structured state across nodes; each node returns simple strings. This keeps things simple but limits richer behaviors (e.g., tool traces, citations, per‑person results as objects).

## Recommendations (Short‑Term)

1. Enrich the faculty subgraph with an internal intent router (email, department, designation, profile/summary, publications, etc.) and map to `FacultyAgent` tools.
2. Add light telemetry around routing decisions (input, label, fallback used) for test visibility and future evaluation.
3. Keep code simple: prefer plain functions and thin nodes; let agents stay self‑contained while nodes orchestrate.
4. Add minimal memory only where it pays off (e.g., remember last resolved person across follow‑ups).

---

## Implementation — LLM‑Based Routing (Done)

We replaced keyword routers with LLM classifiers and kept keyword fallbacks for safety.

- Classifiers live in `multiagent/routing/classifiers.py` with in‑memory caching and strict label validation.
- `supervisor.py` and `student.py` now route via `classify_supervisor` and `classify_student` respectively.
- Tests include `multiagent/tests/test_routing_llm.py` (mocked labels) and existing end‑to‑end scenarios; all pass.
- Prompts are terse and deterministic; invalid outputs fall back to keyword heuristics.

---

## Plan — Richer Faculty Path (Extensible Subgraph)

Current: Supervisor uses `run_faculty` which wraps a minimal faculty subgraph (single `faculty_info` node invoking `FacultyAgent`). Next, enrich this path with intent routing and tool mapping while keeping the implementation small and testable.

### Proposed Graph

- `faculty_router` (LLM): Classify the faculty intent into labels like `email`, `department`, `designation`, `profile`, `publications`, `education`, `experience`, `extension`, `website`, `hec_supervisor`, `multi_person`, or `summary`.
- `person_resolver` (function): Extract person names from the question and resolve to structured person objects (reuse `FacultyAgent`’s `_find_people_in_query` and name index).
- `faculty_tools_node` (function): Given intent + people, call the relevant tool(s) on `FacultyAgent` (e.g., `_tool_email`, `_tool_department`, etc.) and aggregate string output. If `summary`/`profile` is requested, call `FacultyAgent._generate_person_summary` or a semantic `answer` path.
- `aggregator` (function): Build a final string response that includes per‑person results and handles missing data as `N/A`.

This is intentionally small; you can later add more nodes/agents (e.g., separate `PublicationsAgent` or `HECSupervisorsAgent`) and plug them behind the same router.

### Contract

- Input: `question: str`
- Output: `result: str` (non‑empty), preserving current tests’ expectations (e.g., email presence for “email of …”).
- Error modes: If LLM or tools fail, return a graceful fallback with what was resolved.
- Success criteria: Current multi‑agent tests remain green; add a couple of new tests for other intents (department, designation) and multi‑person queries.

### Steps

1. Add an intent classifier inside the faculty subgraph with labels like `email`, `department`, `designation`, `profile`, `publications`, `education`, `experience`, `extension`, `website`, `hec_supervisor`, `multi_person`, `summary`.
2. Implement `person_resolver` reusing `FacultyAgent` internals to map query → people.
3. Implement `faculty_tools_node` to dispatch to `FacultyAgent` tool methods per intent; use semantic summary for `profile/summary` intents.
4. Wire an `aggregator` to format per‑person results and handle missing data as `N/A`.
5. Tests:
   - Extend `multiagent/tests/test_supervisor.py` with new cases (department, designation, multi‑person email).
   - Add `multiagent/tests/test_faculty_graph.py` to unit‑test the faculty subgraph with mocked intent labels.

### Files to add/change

- Update: `multiagent/nodes/faculty.py` (add intent router and tool mapping)
- Update: `multiagent/graph/supervisor.py` (no change expected beyond wiring already in place)
- New tests: `multiagent/tests/test_faculty_graph.py`

### Keep It Simple

- Prefer plain functions for intent classification and person resolution.
- Reuse `FacultyAgent` functions; don’t fork the logic.
- Return plain strings from nodes to maintain compatibility with existing consumers and tests.

---

## Optional: Memory (Later)

- Add a checkpointer and persistent memory to the supervisor graph to track last resolved person(s) and prior intents for follow‑up questions.
- Start with a minimal dict‑based memory keyed by a session ID; only persist short, structured fields.

## Rollout Strategy

1. LLM routing with strict prompts and fallbacks — Done.
2. Enrich the faculty subgraph with minimal intents first (email, department, summary), then add more incrementally.
3. Add memory only if you need multi‑turn continuity.

## Acceptance Criteria (Summary)

- All existing tests remain green.
- New router classifier tests pass deterministically.
- Faculty subgraph (enriched) can answer at least: email, department, summary; and supports multi‑person queries.
- No streaming regressions; non‑empty outputs are guaranteed by fallbacks.
