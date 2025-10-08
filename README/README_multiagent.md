# Hierarchical Multi-Agent Assistant (LangGraph)

This directory contains a LangGraph-based hierarchical multi-agent system for your university assistant.

## Architecture

- Supervisor (router): Top-level graph that routes a user question to either:

  - Student node (which further routes to General or Degree Advisor),
  - Faculty node, or
  - Direct node for greetings/thanks.

- Student node: Wraps existing agents

  - GeneralAgent (RAG over university knowledge)
  - DegreeAdvisorAgent (degree tools + RAG)

- Faculty node: Wraps the FacultyAgent (structured + semantic).

- Memory: You can wire a LangGraph checkpointer (e.g., SQLite or Redis) to persist state and do context-driven routing later.

## Directory structure

```
multiagent/
  graph/
    supervisor.py        # Top-level supervisor graph (router)
  nodes/
    student.py           # Student subgraph: routes to general vs degree advisor
    faculty.py           # Faculty node
  agents/
    student_agent.py     # Thin accessors/wrappers (optional)
  prompts/
    student.py           # Router prompt (placeholder)
    general.py
    degree_advisor.py
  memory/
    ...                  # Placeholders for future checkpointers or memory utils
  tests/
    test_supervisor.py   # Basic integration tests for routing
```

## How it works

- Routing is simple keyword-based for now (cheap and deterministic). Replace `_route_supervisor` and `_route_student` with LLM-based classifiers if desired.
- Each node uses your existing agents (`general_agent.RAGEngine`, `degree_advisor_agent.DegreeAdvisorAgent`, `faculty_agent.FacultyAgent`).
- Streaming is disabled in nodes for clean test assertions; CLI paths can still stream.

## Run tests

In your Conda env `fyp`:

- Pytest will run the new multi-agent tests along with existing ones.

## Extend

- Add new mid-level nodes under `nodes/` and wire them in `graph/supervisor.py`.
- Add new subagents (e.g., under student) and extend the router in `nodes/student.py`.
- Add prompts in `prompts/` and swap keyword routing for LLM-based classification.
- Plug memory by creating a checkpointer and passing it to graph.compile(checkpointer=...).

## Notes

- This is a scaffold to get you started. It intentionally keeps the routing logic lightweight and uses your working agents as-is so you can iterate quickly.
