# CampusHive System Architecture

This document provides a comprehensive overview of the CampusHive system architecture, detailing its layered design from the user interface to the intelligent agent core.

## 1. High-Level Overview

CampusHive is a hierarchical, multi-agent university assistant built on a modern, decoupled architecture. The system is designed to be modular, scalable, and maintainable.

- **Frontend**: A lightweight, single-page web interface for user interaction.
- **Backend**: A robust FastAPI application serving the API, handling authentication, and managing chat persistence.
- **Database**: A relational SQLite database for storing user data, chat history, and file metadata.
- **Intelligence Layer**: A sophisticated multi-agent system orchestrated by LangGraph, responsible for understanding and responding to user queries.
- **Data & Retrieval Layer**: A hybrid retrieval system combining vector search (RAG) and structured data lookups to provide grounded, accurate answers.

The diagram below illustrates the primary architectural layers and the flow of information.

+-------------------------------------------------------------------------------------------------+
| User Interface |
| (Frontend: index.html) |
+---------------------------------------------+---------------------------------------------------+
|
| (REST API Calls, File Uploads)
v
+-------------------------------------------------------------------------------------------------+
| Backend API (FastAPI) |
| |
| +------------------------+ +----------------------+ +------------------------------+ |
| | API Routers |----->| Authentication (JWT) | | File Upload Endpoint | |
| | (/auth, /chats, /multiagent) | +----------------------+ | (/upload) | |
| +------------------------+ +--------------+---------------+ |
| | | |
| | (Invokes Agent) | (Saves File) | (Writes Metadata)
| v v v
+----------------------------------+-----------------------------+----------------+----------------+
| Intelligence Layer | | Persistence Layer |
| (Multi-Agent Core) | | |
| | | +---------------------------+ |
| +----------------------------+ | | | Database (SQLite) | |
| | Supervisor Graph (LangGraph) | | | | (campushive.db) | |
| +-------------+--------------+ | | +---------------------------+ |
| | | | +---------------------------+ |
| | (Routes to) | | | File Storage | |
| +------------+-----------+ | | | (data/uploads/) | |
| v v | | +---------------------------+ |
| +-----------------+ +-----------------+ | |
| | Student Subgraph| | Faculty Subgraph| | |
| +-------+---------+ +--------+--------+ | |
| | | | |
| | (Delegates to) | (Delegates to) | |
| v v | |
| +------------------------------------------------------------+ | |
| | Specialized Agents (RAGEngine, DegreeAdvisor, FacultyAgent) | | |
| +---------------------------------+----------------------------+ | |
| | | |
| | (Retrieves from, Uses Context from) | |
| v | |
+------------------------------------------------------------------+---------------------------------+
| Data & Retrieval Layer (RAG) |
| |
| +--------------------------+ +--------------------------------+ +------------------------------+ |
| | Vector Store Manager | | Document Parser | | Static Data Sources | |
| | (ChromaDB) | | (PDF, DOCX, TXT) | | (JSON, MD, CSV) | |
| +--------------------------+ +--------------------------------+ +------------------------------+ |
| ^ ^ |
| | (Retrieves) | (Indexes) |
| +-------------------------------------------------------------------+ |
+-----------------------------------------------------------------------------------------------------+

## 2. Architectural Layers

### 2.1. Frontend (UI Layer)

- **Technology**: Vanilla HTML, CSS, and JavaScript.
- **Location**: `app/static/index.html`
- **Functionality**:
  - Provides the primary chat interface for users.
  - Handles user authentication state.
  - Sends user messages to the backend API.
  - **File Uploads**: Includes a UI component to select local files. On send, it first uploads the file to a dedicated endpoint and then sends the message with a reference to the uploaded file.

### 2.2. Backend (API & Authentication Layer)

- **Technology**: FastAPI
- **Core Components**:
  - **API Routers (`app/routers/`)**: Exposes endpoints for authentication (`auth.py`), chat session management (`chats.py`), and agent interaction (`multiagent.py`).
  - **Authentication (`app/auth/`)**: Implements JWT-based authentication with password hashing (bcrypt). It secures endpoints and manages user roles.
  - **File Upload Endpoint (`app/routers/chats.py`)**: A dedicated endpoint (`POST /api/v1/chats/{session_id}/upload`) handles multipart file uploads, performs security validation (MIME types), and saves files to a session-specific directory.

### 2.3. Database (Persistence Layer)

- **Technology**: SQLite with SQLAlchemy ORM.
- **Location**: `data/campushive.db`
- **Models (`app/database/models.py`)**:
  - `User`: Stores user credentials and roles.
  - `ChatSession`: Represents a single conversation.
  - `ChatMessage`: Stores individual messages within a session.
  - `UploadedFile`: A new model to track metadata for uploaded files, including filename, server path, and the session it belongs to.

### 2.4. Intelligence Layer (Multi-Agent Core)

#### Dual-Mode Supervisor Architecture

The system employs two supervisor modes that work together:

**A. Planning Supervisor (`multiagent/graph/planning_supervisor.py`)**

- **Purpose**: Handles complex, multi-step queries requiring user clarification or sequential tool calls
- **Implementation**: LangGraph ReAct agent with MemorySaver checkpointer
- **Features**:
  - Human-in-the-loop support with state resumption
  - Scratchpad for visible reasoning steps
  - Tool delegation to domain-specific agents
  - Complexity detection via LLM classification
- **Tools**: `query_student_domain`, `query_faculty_domain`, `query_exam_domain`, `request_clarification`
- **When Used**: User-specific requests (timetables with electives), multi-step aggregation, conditional queries

**B. Legacy Hierarchical Supervisor (`multiagent/graph/supervisor.py`)**

- **Purpose**: Fast path for simple, direct queries
- **Implementation**: Command-based delegation pattern with LangGraph
- **Features**:
  - Single LLM call for routing decision
  - Direct delegation to worker nodes
  - Lower latency for straightforward queries
- **When Used**: Simple lookups, greetings, single-domain questions

**Integration**: `supervisor.py` serves as the entry point, delegating to `planning_supervisor` for complex queries or routing directly for simple ones.

#### Domain Supervisors & Agents

**Student Domain (`multiagent/graph/student_supervisor.py`)**

- Routes to: `general_info`, `timetable`, `degree_advisor`
- Handles: Admissions, courses, programs, schedules, facilities

**Faculty Domain (`multiagent/graph/faculty_supervisor.py`)**

- Uses: `FacultyReactAgent` with structured tools
- Handles: Faculty info, contact details, OBE mappings

**Specialized Agents (`multiagent/agents/`)**:

- `general_agent.py`: General university information (RAG-based)
- `degree_advisor_agent.py`: Degree programs, semester courses (RAG-based)
- `timetable_agent.py`: Course schedules, room assignments (CSV + fuzzy matching)
- `faculty_react_agent.py`: Faculty queries with tools (ReAct pattern)
- `exam_react_agent.py`: Exam generation with context awareness (ReAct pattern)
- `obe_agent/`: CLO-PLO mappings and outcome-based education

**Conversation Memory (`multiagent/memory/manager.py`)**:

- Thread-safe manager with safeguards (max_sessions=1000, TTL=24h)
- Auto-cleanup of stale sessions
- Context passing to all agents (last N turns)
- Loads history from database for persistent memory across sessions

### 2.5. Data & Retrieval Layer (RAG)

- **Vector Stores (`vector_store_manager.py`)**: A centralized manager for creating and accessing ChromaDB vector stores. It uses a hybrid retrieval strategy (BM25 + Vector Similarity + MMR).
- **Store Types**: `GENERAL`, `DEGREE_PROGRAMS`, `FACULTY`.
- **Static Data Sources**: The vector stores are built from curated documents located in `data/general/`, `data/degree_programs/`, and `data/faculty/`.
- **Document Parsing (`multiagent/utils/document_parser.py`)**: A utility to extract text content from uploaded files (PDF, DOCX, TXT). This allows the system to use user-provided documents as context for a query.

## 3. Core Data Flows

### 3.1. Standard Chat Message (Simple Query)

1.  **Frontend**: User sends a message. A `POST` request is made to `/api/v1/multiagent/chat` with the question and session ID.
2.  **Backend**: The endpoint authenticates the user and loads conversation history from database into `MemoryManager`.
3.  **Complexity Detection**: System determines if query is SIMPLE or COMPLEX using LLM-based classification.
4.  **For SIMPLE queries**:
    - Supervisor analyzes question via single LLM call
    - Returns `Command(goto=worker_agent)` to delegate directly
    - Worker executes (e.g., `general_info_node` → `RAGEngine`)
    - Agent retrieves from vector store, synthesizes answer with LLM
5.  **Response**: Result streams back to frontend, saved to database

### 3.2. Complex Query with Planning Mode

1.  **Frontend**: User sends complex request (e.g., "I'm in 7th semester BS AI, give me my timetable")
2.  **Backend**: Loads history, detects COMPLEX via LLM
3.  **Planning Supervisor**: ReAct agent activates with scratchpad
4.  **Multi-Step Execution**:
    - Step 1: Calls `query_student_domain("What courses in 7th semester BS AI?")`
    - Step 2: Observes result has electives → needs clarification
    - Step 3: Calls `request_clarification("Which electives?")` → Returns `__AWAITING_USER_INPUT__` marker
5.  **Human-in-the-Loop**:
    - System pauses, saves state to LangGraph checkpointer
    - Frontend receives `awaiting_user_input: true` event
    - Displays "🤔 Need Your Input" prompt
    - User responds with electives
6.  **State Resumption**:
    - Frontend sends response with `user_input_mode: true`
    - Backend loads checkpointed state via `agent.aget_state()`
    - Appends user message, calls `agent.aupdate_state()`
    - Resumes execution with full context
7.  **Continuation**:
    - Agent continues with user's info
    - Calls additional tools as needed
    - Synthesizes final answer
8.  **Response**: Complete result with scratchpad steps, streamed to frontend, saved to database

### 3.3. Recent System Improvements (Oct 2025)

#### A. Memory System Enhancements

- **Safeguards Added**: max_sessions=1000, session_ttl_hours=24
- **Auto-cleanup**: Stale session removal, LRU eviction
- **Monitoring**: `get_memory_stats()` for system health

#### B. Planning Mode Human-in-the-Loop Fix

- **Problem**: Agent would restart from scratch after user provided clarification
- **Solution**:
  - LangGraph state resumption with `aget_state`/`aupdate_state`
  - Frontend tracks `awaitingUserInput` flag, sends `user_input_mode: true`
  - System prompt enhanced to prevent echoing user input
- **Result**: Seamless multi-turn clarification conversations

#### C. Tool Usage Cleanup

- **Problem**: Planning supervisor was using web search for university data, causing hallucinations
- **Solution**:
  - Removed `query_web_search` from available tools
  - Updated prompt: ALL university data goes through `query_student_domain`
  - Clear tool responsibility boundaries
- **Result**: No more fabricated timetables or course data

## 4. Future Development Plan

### Enriching the Faculty Path

The current faculty subgraph is minimal. The next step is to build it out with a dedicated intent router to handle more specific queries.

- **Proposed Graph**:
  - `faculty_router` (LLM): Classify intent into labels like `email`, `department`, `publications`, `profile`, etc.
  - `person_resolver` (Function): Extract and resolve person names from the query.
  - `faculty_tools_node` (Function): Execute the appropriate `FacultyAgent` tool based on the classified intent.
  - `aggregator` (Function): Format the results into a coherent response.
- **Goal**: Enable the faculty path to answer multi-intent and multi-person queries robustly, such as "What are the email addresses and departments for Dr. Smith and Professor Jones?"

### Persistent Memory

- **Goal**: Implement checkpointing in the LangGraph supervisor to persist state between turns.
- **Use Case**: Allow for true multi-turn contextual conversations, such as remembering the last-mentioned faculty member ("What about his publications?").
- **Implementation**: Utilize a `Checkpointer` (e.g., `LangGraph`'s built-in SQLite checkpointer) connected to the supervisor graph, keyed by session ID.
