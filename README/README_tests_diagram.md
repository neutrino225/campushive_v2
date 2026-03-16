# CampusHive Test Suite Overview

High-level map of the `tests/` directory so you can see what coverage already exists and where to add new cases. The diagram uses Mermaid and renders on GitHub.

```mermaid
flowchart TD
    root[tests/]
    config[pytest.ini<br/>markers, coverage -> reports]
    fixtures[conftest.py<br/>Langfuse callbacks, TestClient, DB sessions]
    agents[agent_tests/]
    apis[api_tests/]
    reports[reports/<br/>html report + coverage]

    root --> config
    root --> fixtures
    root --> agents
    root --> apis
    root --> reports
    config --> reports
    fixtures --> agents
    fixtures --> apis

    subgraph Agent Tests
        a1[test_exam_react.py<br/>multi-turn ReAct streaming]
        a2[test_clean_exam.py<br/>output sanitization (no tools/blank answers)]
        a3[test_exam_validation.py<br/>role-based structure + answer key checks]
        a4[test_exam_routing.py<br/>supervisor routes -> exam path]
        a5[test_obe_agent.py<br/>CLO/PLO mapping + edge cases]
        a6[test_exam_agent.py<br/>legacy exam agent removed]
        a7[test_*streaming*.py<br/>streamed exam demos + chunking]
    end

    subgraph API Tests
        b1[test_auth.py<br/>signup/login guards + token use]
        b2[test_chats.py<br/>chat session CRUD + ownership]
        b3[test_users.py<br/>/auth/me + admin-only user access]
        b4[test_admin.py<br/>vector store admin protections]
        b5[test_multiagent.py<br/>/multiagent/chat streaming + sessions]
    end
```

Tips for keeping the diagram accurate:

- Add a short description next to each new test module; keep labels brief so the boxes stay readable.
- Update `pytest.ini` markers if you introduce new suites (e.g., `performance`, `load`) and mirror them in the diagram.
- Regenerate HTML/coverage reports with `pytest -v --cov` so `tests/reports/` stays in sync with the suite.
