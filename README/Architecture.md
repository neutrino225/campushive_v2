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

- **Orchestration**: LangGraph (`multiagent/graph/supervisor.py`)
  - The `SupervisorState` TypedDict defines the shared state that flows through the graph, including the user's question, conversation history, and any file-based context.
- **Routing**: LLM-based classifiers (`multiagent/routing/classifiers.py`) with keyword-based fallbacks determine the user's intent and route the query to the appropriate subgraph (e.g., `student` or `faculty`).
- **Agents (`multiagent/agents/`)**:
  - `RAGEngine`: Handles general knowledge questions using the main university vector store.
  - `DegreeAdvisorAgent`: Answers queries about degree programs.
  - `FacultyAgent`: Provides specific information about faculty members using structured tools.
- **Conversation Memory (`multiagent/memory/manager.py`)**: A thread-safe manager that loads conversation history from the database into a short-term memory for the agents to use, ensuring contextual follow-up answers.

### 2.5. Data & Retrieval Layer (RAG)

- **Vector Stores (`vector_store_manager.py`)**: A centralized manager for creating and accessing ChromaDB vector stores. It uses a hybrid retrieval strategy (BM25 + Vector Similarity + MMR).
- **Store Types**: `GENERAL`, `DEGREE_PROGRAMS`, `FACULTY`.
- **Static Data Sources**: The vector stores are built from curated documents located in `data/general/`, `data/degree_programs/`, and `data/faculty/`.
- **Document Parsing (`multiagent/utils/document_parser.py`)**: A utility to extract text content from uploaded files (PDF, DOCX, TXT). This allows the system to use user-provided documents as context for a query.

## 3. Core Data Flows

### 3.1. Standard Chat Message

1.  **Frontend**: User sends a message. A `POST` request is made to `/api/v1/multiagent/invoke` with the question and session ID.
2.  **Backend**: The `invoke_multiagent` endpoint authenticates the user and loads the conversation history from the database into the `MemoryManager`.
3.  **Agent Core**: The supervisor graph is invoked with the user's question and conversation history.
4.  **Routing**: The supervisor's router classifies the intent and passes the state to a subgraph (e.g., `student_node`).
5.  **Delegation**: The subgraph's router further refines the intent and delegates to a specialized agent (e.g., `RAGEngine`).
6.  **Retrieval & Generation**: The agent retrieves relevant information from its vector store, synthesizes an answer with the LLM, and returns the result.
7.  **Response**: The result propagates back up the graph, is streamed back to the frontend, and the message exchange is saved to the database.

### 3.2. Chat Message with File Upload

This flow extends the standard flow by injecting file content as context.

1.  **Frontend**: User selects a file and types a message. On send:
    a. A `POST` request containing the file is sent to `/api/v1/chats/{session_id}/upload`.
    b. The backend saves the file to `data/uploads/<session_id>/` and creates a record in the `UploadedFile` database table, returning a `file_id`.
    c. A `POST` request is sent to `/api/v1/multiagent/invoke` with the question, session ID, and the new `file_id`.
2.  **Backend**: The `invoke_multiagent` endpoint receives the `file_id`. It queries the database to find the file's path.
3.  **Parsing**: It calls `document_parser.parse_document()` to extract the text content from the file.
4.  **Agent Core**: The supervisor graph is invoked with the standard state **plus** the extracted text in the `file_context` field.
5.  **Contextual Invocation**: The agent nodes (e.g., `student_node`) check for `file_context`. If present, they prepend the document's content to the user's question, forming an "enhanced question."
6.  **Response**: The agent processes the enhanced question, using the provided text as primary context. The rest of the flow proceeds as normal.

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
