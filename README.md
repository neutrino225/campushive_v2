# CampusHive — Final Year Project

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Authentication](https://img.shields.io/badge/Auth-JWT-orange.svg)](docs)

CampusHive is a multi-agent university assistant designed for campus and academic information retrieval. It routes user questions through a top-level supervisor into student and faculty subgraphs and uses retrieval-augmented generation (RAG) for grounded answers.

## ✨ New: Authentication System

CampusHive now includes a complete authentication and chat management system with:

- 🔐 JWT-based user authentication
- 👥 Role-based access control (student, faculty, admin)
- 💬 Persistent chat sessions
- 📊 Admin dashboard for user management

**See [QUICKSTART.md](QUICKSTART.md) for authentication setup and usage.**

## Quick overview

**Delegation-Based Multi-Agent Architecture**

CampusHive uses LangGraph's Command-based delegation pattern for intelligent query routing:

- **Supervisor**: Makes a single LLM call to analyze the question and delegates via `Command(goto=agent_name)`
- **Worker Agents**: Specialized agents (student, faculty, exam, obe) execute and return results
- **Student path**: General RAG assistant (`RAGEngine`) + `DegreeAdvisorAgent` for degree programs
- **Faculty path**: `FacultyReactAgent` with structured tools (email, department, publications, research)
- **Exam path**: `ExamReactAgent` for quiz/exam generation (faculty/admin only)
- **OBE path**: `OBEAgent` for CLO-PLO outcome mapping

Vector stores are managed centrally via `vector_store_manager.py` (Chroma + BM25 + MMR ensemble).

## Getting started

Prerequisites

- Python 3.10+
- Conda environment recommended

Install dependencies

```bash
conda activate fyp
pip install -r requirements.txt
```

Environment

- Copy `.env.example` to `.env` and fill in `GROQ_API_KEY` (required).

Initialize database (for authentication)

```bash
python scripts/init_db.py
python scripts/create_admin.py
```

Start the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Access the application

- **Main App**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

Run the supervisor (quick test)

```bash
python -c "from multiagent.graph.supervisor import run_supervisor; print(run_supervisor('Who is the head of computer science?'))"
```

Vector stores

- Vector stores live under `data/vector_stores/`. Use `vector_store_manager.py` to create or refresh stores:

```bash
python vector_store_manager.py --action create
```

Testing

- Run tests with pytest:

```bash
pytest -q
```

## Exam/Quiz Generator (Debug Script)

A dedicated CLI is available to generate exams or quizzes with pretty streaming output and optional diagnostics:

```bash
scripts/exam_cli.py --query "Generate a final exam for Data Structures (100 marks) focusing on trees and graphs" --role faculty
```

Options:

- --query / -q: Natural language request (required)
- --role / -r: student | faculty (default: student)
- --session / -s: Custom session id (optional)
- --verbose / -v: Show extra routing and timing info

Repository layout (top-level)

- `app/` — FastAPI application with authentication and chat management
  - `database/` — SQLAlchemy models and database connection
  - `auth/` — Authentication utilities (JWT, password hashing)
  - `schemas/` — Pydantic request/response models
  - `routers/` — API endpoints (auth, chat, admin, multiagent)
  - `static/` — Frontend static files
- `multiagent/` — graphs, nodes, agents, routing classifiers, and tests
- `data/` — scraped data, vector stores, and SQLite database
- `scrapers/` — scrapers to populate `data/`
- `scripts/` — utility scripts (init_db, create_admin, tests)
- `vector_store_manager.py` — building and managing vector stores
- `config.py` — LLM and embeddings configuration

More docs

- Exam Agent end-to-end: [README/README_exam_agent.md](README/README_exam_agent.md)

## 🔐 Authentication System

### Features

- **User Management**: Signup, login, and role-based access
- **Chat Persistence**: Store and retrieve conversation history
- **Admin Panel**: Manage users and permissions
- **Secure**: JWT tokens, bcrypt passwords, role-based access control

### API Endpoints

#### Authentication

- `POST /auth/signup` - Register new user
- `POST /auth/login` - Login and get JWT token
- `GET /auth/me` - Get current user info
- `POST /auth/logout` - Logout

#### Chat Management

- `GET /chats` - List user's chat sessions
- `POST /chats` - Create new chat session
- `GET /chats/{id}` - Get chat with messages
- `POST /chats/{id}/messages` - Add message
- `DELETE /chats/{id}` - Delete chat session

#### Admin (admin role required)

- `GET /admin/users` - List all users
- `PUT /admin/users/{id}/role` - Update user role
- `DELETE /admin/users/{id}` - Delete user

### Quick Example

```bash
# Signup
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"username":"john","email":"john@example.com","password":"Pass123!"}'

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"john","password":"Pass123!"}'

# Use the token from login response
TOKEN="your_jwt_token_here"

# Create chat session
curl -X POST http://localhost:8000/chats \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_name":"My Chat"}'
```

### Documentation

- **Quick Start**: [QUICKSTART.md](QUICKSTART.md)
- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Implementation**: [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md)
- **Checklist**: [CHECKLIST.md](CHECKLIST.md)
- **Summary**: [SUMMARY.md](SUMMARY.md)

Contributing

- Open an issue or a PR. Add tests for new behavior.

License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.
