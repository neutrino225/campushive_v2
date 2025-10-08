# CampusHive Authentication System Architecture

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                             │
│  ┌────────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │  Web Browser   │  │ Mobile App   │  │  API Client       │   │
│  │  (React/Vue)   │  │              │  │  (Python/JS)      │   │
│  └────────┬───────┘  └──────┬───────┘  └─────────┬─────────┘   │
└───────────┼──────────────────┼────────────────────┼─────────────┘
            │                  │                    │
            └──────────────────┼────────────────────┘
                               │
                    HTTP/HTTPS (JSON)
                               │
┌──────────────────────────────┼─────────────────────────────────┐
│                       API LAYER (FastAPI)                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Middleware                                  │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │     CORS     │  │   Logging    │  │   Exception  │  │   │
│  │  │  Middleware  │  │  Middleware  │  │   Handler    │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                               │                                  │
│  ┌────────────────────────────┼──────────────────────────────┐ │
│  │                      ROUTERS                              │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐ │ │
│  │  │   /auth     │  │   /chats    │  │  /admin/users    │ │ │
│  │  │  - signup   │  │  - create   │  │  - list users    │ │ │
│  │  │  - login    │  │  - list     │  │  - update role   │ │ │
│  │  │  - logout   │  │  - get      │  │  - delete user   │ │ │
│  │  │  - me       │  │  - delete   │  │                  │ │ │
│  │  └─────────────┘  └─────────────┘  └──────────────────┘ │ │
│  │         │                │                   │            │ │
│  │         └────────────────┼───────────────────┘            │ │
│  └──────────────────────────┼──────────────────────────────┐ │
│                              │                                │ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              AUTHENTICATION LAYER                        │ │
│  │  ┌──────────────────────────────────────────────────┐   │ │
│  │  │  Dependencies (get_current_user, require_admin)  │   │ │
│  │  └──────────────────┬───────────────────────────────┘   │ │
│  │                     │                                    │ │
│  │  ┌──────────────────▼───────────────────────────────┐   │ │
│  │  │           Security Utilities                      │   │ │
│  │  │  - Password hashing (bcrypt)                     │   │ │
│  │  │  - JWT token creation/validation                 │   │ │
│  │  │  - Role verification                              │   │ │
│  │  └──────────────────────────────────────────────────┘   │ │
│  └─────────────────────────────────────────────────────────┘ │
│                              │                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              SCHEMA LAYER (Pydantic)                     │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │ │
│  │  │   Auth       │  │    Chat      │  │    Admin     │  │ │
│  │  │  Schemas     │  │  Schemas     │  │  Schemas     │  │ │
│  │  │  - UserSignup│  │  - ChatCreate│  │  - RoleUpdate│  │ │
│  │  │  - UserLogin │  │  - ChatMsg   │  │              │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────┼──────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────┐
│                    DATABASE LAYER (SQLAlchemy)                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                   ORM Models                             │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │ │
│  │  │    User      │  │ ChatSession  │  │ ChatMessage  │  │ │
│  │  │              │  │              │  │              │  │ │
│  │  │ - id         │  │ - id         │  │ - id         │  │ │
│  │  │ - username   │  │ - user_id    │  │ - session_id │  │ │
│  │  │ - email      │  │ - name       │  │ - type       │  │ │
│  │  │ - password   │  │ - timestamps │  │ - content    │  │ │
│  │  │ - role       │  │              │  │ - agent_type │  │ │
│  │  │ - timestamps │  │              │  │ - timestamp  │  │ │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │ │
│  └─────────┼──────────────────┼──────────────────┼─────────┘ │
│            │                  │                  │            │
│            │    Foreign Keys  │                  │            │
│            └──────────────────┼──────────────────┘            │
│                               │                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Database Connection                         │ │
│  │        SessionLocal / get_db() dependency                │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────┼──────────────────────────────┘
                               │
                     ┌─────────▼─────────┐
                     │   SQLite Database  │
                     │  campushive.db     │
                     │  (data/directory)  │
                     └────────────────────┘
```

## Request Flow Diagram

### 1. User Signup Flow

```
┌──────┐     POST /auth/signup      ┌─────────┐
│Client├──────────────────────────► │  Auth   │
└──────┘   {username, email, pwd}   │ Router  │
                                     └────┬────┘
                                          │
                                   Validate Input
                                          │
                                    ┌─────▼─────┐
                                    │  Hash     │
                                    │ Password  │
                                    └─────┬─────┘
                                          │
                                    ┌─────▼─────┐
                                    │  Create   │
                                    │   User    │
                                    │(role=student)
                                    └─────┬─────┘
                                          │
                                    ┌─────▼─────┐
                                    │ Generate  │
                                    │    JWT    │
                                    └─────┬─────┘
                                          │
┌──────┐   {token, user_info}      ┌─────▼─────┐
│Client│◄──────────────────────────┤  Return   │
└──────┘                            │  Token    │
                                    └───────────┘
```

### 2. Protected Endpoint Flow

```
┌──────┐     GET /chats             ┌─────────┐
│Client├──────────────────────────► │  Chat   │
└──────┘   Header: Bearer TOKEN     │ Router  │
                                     └────┬────┘
                                          │
                                   ┌──────▼──────┐
                                   │Dependency:  │
                                   │get_current_ │
                                   │   user()    │
                                   └──────┬──────┘
                                          │
                                   ┌──────▼──────┐
                                   │  Decode     │
                                   │    JWT      │
                                   └──────┬──────┘
                                          │
                              ┌───────────▼───────────┐
                              │  Valid?               │
                              └───────┬───────────────┘
                                  Yes │     │ No
                         ┌────────────┘     └────────┐
                         │                            │
                    ┌────▼────┐                 ┌────▼────┐
                    │ Get User│                 │  401    │
                    │from DB  │                 │ Denied  │
                    └────┬────┘                 └─────────┘
                         │
                    ┌────▼────┐
                    │ Execute │
                    │Endpoint │
                    └────┬────┘
                         │
┌──────┐           ┌────▼────┐
│Client│◄──────────┤ Return  │
└──────┘           │  Data   │
                   └─────────┘
```

### 3. Admin Endpoint Flow

```
┌──────┐   PUT /admin/users/2/role  ┌─────────┐
│Client├──────────────────────────► │  Admin  │
└──────┘   Header: Bearer TOKEN     │ Router  │
           Body: {role: "faculty"}   └────┬────┘
                                          │
                                   ┌──────▼──────┐
                                   │Dependency:  │
                                   │require_admin│
                                   └──────┬──────┘
                                          │
                              ┌───────────▼───────────┐
                              │  Is Admin?            │
                              └───────┬───────────────┘
                                  Yes │     │ No
                         ┌────────────┘     └────────┐
                         │                            │
                    ┌────▼────┐                 ┌────▼────┐
                    │ Update  │                 │  403    │
                    │  Role   │                 │Forbidden│
                    └────┬────┘                 └─────────┘
                         │
┌──────┐           ┌────▼────┐
│Client│◄──────────┤ Return  │
└──────┘           │ Updated │
                   │  User   │
                   └─────────┘
```

## Data Flow

### Chat Session Creation & Message Storage

```
User Action                 Backend Processing                 Database

┌──────────┐
│ Create   │
│ Session  │
└────┬─────┘
     │
     ├────────► Validate Token ────────► Check User
     │                                    in DB
     │
     ├────────► Create Session ─────────► INSERT INTO
     │          Record                    chat_sessions
     │                                    (user_id, name)
     │
     ◄─────────── Return Session ID

┌──────────┐
│  Send    │
│ Message  │
└────┬─────┘
     │
     ├────────► Validate Session ───────► Check Session
     │          Ownership                 belongs to User
     │
     ├────────► Store Message ───────────► INSERT INTO
     │                                     chat_messages
     │                                     (session_id,
     │                                      content, type)
     │
     ├────────► Update Session ──────────► UPDATE
     │          Timestamp                  chat_sessions
     │                                     SET updated_at
     │
     ◄─────────── Return Message
```

## Security Layers

```
┌───────────────────────────────────────────────────┐
│              Security Layer 1                      │
│              Input Validation                      │
│  - Pydantic schemas validate all input             │
│  - Email format checking                           │
│  - Username format (alphanumeric + _)              │
│  - Password strength requirements                  │
└─────────────────┬─────────────────────────────────┘
                  │
┌─────────────────▼─────────────────────────────────┐
│              Security Layer 2                      │
│            Password Hashing                        │
│  - Bcrypt with automatic salting                   │
│  - No plain passwords stored                       │
│  - One-way hash function                           │
└─────────────────┬─────────────────────────────────┘
                  │
┌─────────────────▼─────────────────────────────────┐
│              Security Layer 3                      │
│              JWT Tokens                            │
│  - HS256 algorithm                                 │
│  - 24-hour expiration                              │
│  - Payload: {user_id, role, exp}                   │
└─────────────────┬─────────────────────────────────┘
                  │
┌─────────────────▼─────────────────────────────────┐
│              Security Layer 4                      │
│          Role-Based Access Control                 │
│  - Middleware checks user role                     │
│  - Admin endpoints protected                       │
│  - Resource ownership validation                   │
└─────────────────┬─────────────────────────────────┘
                  │
┌─────────────────▼─────────────────────────────────┐
│              Security Layer 5                      │
│            SQL Injection Prevention                │
│  - SQLAlchemy ORM (parameterized queries)          │
│  - No raw SQL with user input                      │
│  - Automatic escaping                              │
└───────────────────────────────────────────────────┘
```

## Component Dependencies

```
main.py
  ├── routers/
  │   ├── auth.py
  │   │   ├── database/models.py
  │   │   ├── schemas/auth.py
  │   │   └── auth/security.py
  │   ├── chats.py
  │   │   ├── database/models.py
  │   │   ├── schemas/chat.py
  │   │   └── auth/dependencies.py
  │   └── user_admin.py
  │       ├── database/models.py
  │       ├── schemas/auth.py
  │       └── auth/dependencies.py
  ├── database/
  │   ├── connection.py
  │   └── models.py
  ├── auth/
  │   ├── security.py
  │   └── dependencies.py
  └── schemas/
      ├── auth.py
      └── chat.py
```

## Deployment Architecture

```
                  ┌─────────────────┐
                  │   Load Balancer  │
                  └────────┬─────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌─────▼──────┐ ┌─────▼──────┐
    │  Uvicorn    │ │  Uvicorn   │ │  Uvicorn   │
    │  Worker 1   │ │  Worker 2  │ │  Worker 3  │
    └──────┬──────┘ └─────┬──────┘ └─────┬──────┘
           │               │               │
           └───────────────┼───────────────┘
                           │
                  ┌────────▼─────────┐
                  │   SQLite DB      │
                  │ (Development)    │
                  │        OR        │
                  │   PostgreSQL     │
                  │  (Production)    │
                  └──────────────────┘
```

## File Structure

```
fyp_test/
├── app/
│   ├── main.py                    [Entry point]
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py          [DB setup]
│   │   └── models.py              [SQLAlchemy models]
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── security.py            [JWT & password]
│   │   └── dependencies.py        [Auth middleware]
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py                [Auth schemas]
│   │   └── chat.py                [Chat schemas]
│   └── routers/
│       ├── auth.py                [Auth endpoints]
│       ├── chats.py               [Chat endpoints]
│       └── user_admin.py          [Admin endpoints]
├── data/
│   └── campushive.db              [SQLite database]
├── scripts/
│   ├── init_db.py                 [DB initialization]
│   ├── create_admin.py            [Admin creation]
│   └── test_auth_api.py           [API tests]
├── requirements.txt               [Dependencies]
├── auth_plan.md                   [Specifications]
├── IMPLEMENTATION_REPORT.md       [Details]
├── QUICKSTART.md                  [Guide]
├── SUMMARY.md                     [Summary]
└── ARCHITECTURE.md                [This file]
```

---

**Last Updated**: October 7, 2025  
**Version**: 1.0  
**Status**: Production Ready (after security review)
