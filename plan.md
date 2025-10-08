## Exam generation feature — implementation plan

This document describes a complete implementation plan to add exam generation capability to the system. Two agents will be extended:

- Student agent: generates mock exams and mock quizzes for students.
- Faculty agent: generates official-looking exams and quizzes in the FAST format. This agent is RBAC-guarded and only available to authenticated users with the `faculty` role.

Goals

- Reuse an existing repository of exams by FAST when available for a requested course.
- If no repository exam exists, generate exam content from the provided topic(s).
- Produce FAST-compatible output for the faculty agent and educational/mock format for the student agent.
- Add safe RBAC guards so only faculty can call the faculty exam generator.

Assumptions (explicit)

- There is an existing vector / content store of exams (the "repository of exams by fast") that we can query. If the exact API doesn't exist yet, we will add a small retrieval helper to `vector_store_manager.py`.
- Agents are invoked from the existing multiagent flow (files under `multiagent/agents/` and the multiagent router in `app/routers/multiagent.py`). If different invocation points exist, adapt the RBAC checks to that entry.

Contract (what each new API/function will do)

- generate_exam(user, mode, fast?, course?, topic?, n_questions?, quiz_only?) ->
  - Inputs:
    - user: object with at least `.id` and `.role` or session token usable for role checks.
    - mode: 'faculty' or 'student' (or 'official'/'mock').
    - fast: optional FAST identifier or course code used to look up repository exams.
    - course: optional human-readable course identifier.
    - topic: optional textual topic/outline to seed generation if no repo exam exists.
    - n_questions: optional number of questions target.
    - quiz_only: boolean -> only produce a quiz when true.
  - Outputs:
    - success: { format: 'FAST'|'MOCK', content: string (FAST markdown / JSON), metadata: {source: 'repository'|'generated', used_fast: <id?>} }
    - error modes: permission_denied (faculty-only), invalid_input, generation_failure, repository_lookup_error.

High-level design

1. Retrieval layer

- Update `vector_store_manager.py` with a `get_exam_for_course(fast_or_course_id)` helper that returns an exam document (raw text / structured). If vector stores (semantic search) exist, prefer a precise lookup; otherwise fall back to file-based lookup under `data/degree_programs/` or `data/vector_stores/`.

2. Exam generator module

- Add `multiagent/exam_generator.py` (small, testable module) that encapsulates logic for:
  - repository retrieval via `vector_store_manager.get_exam_for_course(...)`.
  - prompt selection (faculty FAST prompt vs student mock prompt) using new prompt templates in `multiagent/prompts/exam_generation.py`.
  - calling the LLM wrapper already used across agents (re-use existing LLM helper; if none exists, create a thin wrapper around the configured model call).
  - post-processing the LLM output into standardized return shape above.

3. Prompts

- Add `multiagent/prompts/exam_generation.py` with two main prompt templates:
  - `FAST_EXAM_PROMPT` — strict instructions and FAST-format schema; include examples (2 small questions + metadata) and an instruction to output machine-parseable FAST blocks and a short human summary.
  - `MOCK_EXAM_PROMPT` — instructions for mock exams and quizzes targeted at student practice (less strict formatting allowed, but include a simple machine-parseable JSON or markdown block).

4. Agent changes

- `multiagent/agents/faculty_agent.py`

  - Add a permission guard at the start of the exam generation path: check the `user.role` (or session) and reject requests without `faculty` role with a clear error.
  - Accept parameters (fast/course/topic/n_questions/quiz_only) and call `exam_generator.generate_exam(user, mode='faculty', ...)`.
  - Return FAST output and metadata to the caller.

- `multiagent/agents/student_agent.py`
  - Add a new entry point for `generate_mock_exam(...)` or reuse existing flows; call `exam_generator.generate_exam(user, mode='student', ...)`.
  - No RBAC check (students can call this for practice) but optionally rate-limit or add session-scoped memory usage.

5. Router / API layer

- `app/routers/multiagent.py` (or wherever agent endpoints are routed)
  - For faculty-exam endpoints, add a middleware or inline check to enforce RBAC before calling the agent logic. Prefer reuse of the project-wide auth system (look for existing `current_user` or `get_current_user` functions). If no centralized auth exists, add a helper `require_role(user, 'faculty')` and use it.

6. Tests and QA

- Unit tests (fast, local):

  - `tests/test_vector_store_manager.py::test_get_exam_for_course_found` (mock store, returns expected document)
  - `tests/test_vector_store_manager.py::test_get_exam_for_course_missing` (returns None / raises)
  - `tests/test_exam_generator.py::test_generate_from_repository` (mock LLM, verify source='repository')
  - `tests/test_exam_generator.py::test_generate_from_topic` (mock LLM, no repository)
  - `tests/test_rbac.py::test_faculty_only_endpoint` (simulate a call from non-faculty -> permission_denied)

- Integration smoke tests:
  - Call the faculty endpoint as a faculty user and verify FAST-formatted string returned and HTTP 200.
  - Call the faculty endpoint as a non-faculty user and verify HTTP 403/permission denied.

7. Logging, metrics, telemetry

- Log generation requests with user id, source (repo/generated), course/fast, and n_questions. Record failures and LLM latency in a monitoring histogram.

8. Security and content safety

- Sanitize repository content before including it in prompts (strip dangerous markup or private metadata).
- For faculty FAST output (official-looking exams) include a visible watermark or metadata field (e.g., generated_by_system: true) if policy requires auditability.

Implementation tasks (step-by-step)

Phase A — setup and retrieval (1-2 days)

1. Add `multiagent/exam_generator.py` with stubbed functions and tests.
2. Add `multiagent/prompts/exam_generation.py` and draft FAST and MOCK prompts.
3. Extend `vector_store_manager.py` with `get_exam_for_course(fast_or_course_id)`.
4. Write unit tests for retrieval helpers.

Phase B — connect agents and RBAC (1-2 days)

1. Update `multiagent/agents/faculty_agent.py` to call `exam_generator` and add role check.
2. Update `multiagent/agents/student_agent.py` to call `exam_generator` for mock generation.
3. Update router `app/routers/multiagent.py` (or equivalent) to enforce RBAC consistently.
4. Add integration tests for endpoints.

Phase C — prompt tuning, QA and polish (1-2 days)

1. Run prompt tuning with a few courses from the exam repository and iterate on the FAST prompt until outputs are reliably parseable.
2. Add small post-processing validators that parse FAST output and return structured errors when invalid.
3. Add docs to `README.md` and the project `progress.md` entry.

Files to add or modify (concrete list)

- Add: `plan.md` (this file)
- Add: `multiagent/exam_generator.py` — exam generation core logic
- Add: `multiagent/prompts/exam_generation.py` — FAST and MOCK prompts
- Modify: `vector_store_manager.py` — add `get_exam_for_course(...)`
- Modify: `multiagent/agents/faculty_agent.py` — RBAC + call generator
- Modify: `multiagent/agents/student_agent.py` — call generator
- Modify: `app/routers/multiagent.py` — ensure RBAC in routing layer (if needed)
- Add tests: `tests/test_exam_generator.py`, `tests/test_vector_store_manager.py`, `tests/test_rbac.py`

Edge cases and how to handle them

- Repository exam found but outdated/invalid format: fallback to generation but include `source: 'repository'` with a `validity: false` flag. Log for manual review.
- LLM hallucination or malformed FAST output: validate with a strict parser and return a clear parsing error to caller; optionally attempt a single automatic re-generation with stronger constraints.
- Large or long topics: enforce a maximum topic length and summarise or reject overly long requests.
- Permission bypass attempts: don't trust client-provided role; check server-side session or JWT claims.

Quality gates (minimum before merge)

- All new unit tests pass.
- Lint/type checks pass (project's existing linter/formatting).
- Integration test verifying RBAC (faculty vs non-faculty) passes.
- Manual smoke test producing at least one valid FAST exam from repository and one generated from topic.

Acceptance criteria (definition of done)

- Student agent can generate mock exams/quizzes on request and returns machine-parseable content.
- Faculty agent returns FAST-formatted exams/quizzes and is only callable by faculty users (enforced in router or agent).
- If an exam exists in the repository for the requested course, it is included and used as the primary context for generation.
- Tests and documentation for new behavior are present in the repo.

Next steps (immediate)

1. I can create skeleton files and unit test stubs for the items above (prompts, generator, retrieval helper). If you want, I will implement them next in small commits and run the test suite after each change.
2. Tell me whether you prefer the RBAC enforcement in the router layer (recommended) or inside the agent code itself (defense-in-depth: both is fine). If you have an existing auth helper function name (e.g. `get_current_user`), point it out and I'll reuse it.

Contact / notes
Keep prompts and FAST format examples in the prompt file. If you have a canonical FAST schema or examples, drop them into `multiagent/prompts/exam_generation.py` before tuning.

---

Summary: this plan adds a modular `exam_generator`, safe RBAC checks for the faculty agent, repository retrieval with graceful fallback to LLM generation, tests, and documentation. The design favors small incremental changes with unit tests and clear acceptance criteria.
