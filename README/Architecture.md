# CampusHive Architecture

This document shows the current high-level architecture of CampusHive as implemented in this repository. It focuses on how the web app and mobile app interact with the backend, where the LLM and retrieval layers fit, and which databases and storage systems are in use.

## High-Level Diagram

```mermaid
flowchart LR
    subgraph Clients["Client Applications"]
        WEB["Web Frontend<br/>React + Vite<br/>JWT auth, chat UI, admin dashboard<br/>Streams chat over SSE"]
        MOBILE["Mobile App<br/>Expo + React Native<br/>JWT auth, chat + session UI<br/>Uses JSON chat responses"]
    end

    subgraph Backend["Backend API"]
        FASTAPI["FastAPI application<br/>app/main.py"]
        AUTH["Auth router<br/>/auth<br/>signup, login, me, logout"]
        CHATS["Chat router<br/>/chats<br/>session CRUD + history"]
        MULTI["Multiagent router<br/>/multiagent/chat<br/>SSE or JSON response mode"]
        ADMIN["Admin router<br/>/admin<br/>health, vector stores, exam upload"]
    end

    subgraph Orchestration["AI Orchestration Layer"]
        MEMORY["MemoryManager<br/>in-memory recent context<br/>TTL + session safeguards"]
        SUP["LangGraph supervisors<br/>main supervisor + planning supervisor"]
        AGENTS["Domain agents<br/>Student | Faculty | Exam | OBE | Direct"]
    end

    subgraph Retrieval["Knowledge and Retrieval"]
        VSM["VectorStoreManager<br/>hybrid retrieval<br/>BM25 + embeddings + MMR"]
        CHROMA["Chroma vector stores<br/>general | degree_programs | faculty | exams"]
        STRUCTURED["Structured sources<br/>JSON, Markdown, CSV<br/>degree data, faculty data,<br/>general docs, timetable data"]
        EXAMS["Exam ingestion pipeline<br/>PDF upload -> parse -> structured JSON -> exams store"]
    end

    subgraph Persistence["Persistence and Storage"]
        SQLITE["SQLite<br/>data/campushive.db<br/>users, chat_sessions,<br/>chat_messages, uploaded_exams"]
        FILES["Filesystem storage<br/>data/vector_stores/<br/>data/exams/<br/>repo data/*.json|csv|md"]
    end

    subgraph Models["LLM and Embeddings"]
        LLM["LLM runtime<br/>Groq or OpenAI<br/>default code paths:<br/>Groq openai/gpt-oss-120b<br/>or OpenAI gpt-4o-mini"]
        SMALL["Small routing / helper LLM<br/>Groq llama-3.1-8b-instant<br/>or OpenAI gpt-4o-mini"]
        EMB["Embeddings<br/>OpenAI text-embedding-3-small<br/>or Ollama nomic-embed-text"]
    end

    WEB -->|"HTTPS REST + SSE"| FASTAPI
    MOBILE -->|"HTTPS REST + JSON"| FASTAPI

    FASTAPI --> AUTH
    FASTAPI --> CHATS
    FASTAPI --> MULTI
    FASTAPI --> ADMIN

    AUTH <--> SQLITE
    CHATS <--> SQLITE
    MULTI <--> SQLITE
    ADMIN <--> SQLITE

    MULTI --> MEMORY
    MULTI --> SUP
    SUP --> AGENTS
    AGENTS --> MEMORY

    AGENTS --> VSM
    AGENTS -->|"deterministic timetable lookups"| STRUCTURED
    VSM <--> CHROMA
    STRUCTURED --> VSM
    ADMIN --> EXAMS
    EXAMS --> VSM

    CHROMA <--> FILES
    EXAMS --> FILES
    STRUCTURED --> FILES

    SUP --> LLM
    AGENTS --> LLM
    AGENTS --> SMALL
    VSM --> EMB
```

## How The Pieces Fit Together

- The web frontend and mobile app both use the same FastAPI backend.
- The web app is the richer client today: it uses streaming responses from `/multiagent/chat` and exposes the admin dashboard.
- The mobile app already reuses the same auth, chat session, and multiagent APIs, but currently calls chat in non-streaming JSON mode.
- Authentication is JWT-based, and chat/session data is persisted in SQLite.
- Multi-agent orchestration is handled by LangGraph supervisors, which route requests into student, faculty, exam, OBE, or direct-response paths.
- Conversation context is kept in the in-memory `MemoryManager` and is hydrated from SQLite-backed chat history when requests arrive.

## Data And AI Layers

- RAG-backed domains use Chroma vector stores managed by `vector_store_manager.py`.
- The current vector stores are `general`, `degree_programs`, `faculty`, and `exams`.
- Timetable answers are not purely vector-search based; they also use structured timetable data from local CSV/JSON sources for deterministic lookups.
- Admin exam uploads go through a background processing flow: PDF upload, LLM-assisted structuring, append to `data/structured_exams.json`, then index into the `exams` vector store.
- LLM selection is configurable in [`config.py`](/Users/ninjascode5/FYP/campushive_v2/config.py). In `auto` mode, the code prefers Groq when a `GROQ_API_KEY` is available; otherwise it falls back to OpenAI. Embeddings prefer OpenAI when `OPENAI_API_KEY` is available, otherwise Ollama.

## Main Request Paths

1. Web or mobile sends auth/session/chat requests to FastAPI.
2. FastAPI authenticates the user, loads prior context, and routes chat traffic into the LangGraph supervisor stack.
3. The supervisor either answers directly or delegates to a domain agent.
4. Agents use the LLM plus either vector retrieval, structured timetable data, or exam-processing flows.
5. Final answers are returned to the client and persisted to SQLite with route metadata.

