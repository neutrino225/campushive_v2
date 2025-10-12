# Implementation Plan: Dynamic Document Uploads with Session-Based Vector Stores

This document outlines the revised plan to add file upload functionality to the CampusHive system. This approach will create dynamic, session-specific vector stores for user-uploaded documents, allowing agents to perform context-aware RAG (Retrieval-Augmented Generation) on-the-fly. For instance, a user can upload lecture slides and ask the system to generate a quiz based on the content, leveraging the session-specific vector store for accurate, relevant questions while utilizing conversation memory for follow-up interactions.

---

### **Phase 1: Backend (FastAPI) - File Upload and Vector Store Ingestion**

The first step is to build a backend route that handles file uploads and ingests their content into a dedicated vector store for the current chat session.

1.  **Define a Vector Store Location**:

    - A new directory will be created to house session-specific vector stores: `data/vector_stores/user_uploads/`.
    - Each session will have its own subdirectory, named using a combination of user and session IDs (e.g., `data/vector_stores/user_uploads/user_<user_id>_session_<session_id>/`). This isolates document context per conversation.

2.  **Create a New API Endpoint for Uploads**:

    - A new endpoint will be added to `app/routers/chats.py`: `POST /api/v1/chats/{session_id}/upload`.
    - **Functionality**:
      - It will require user authentication to identify the user.
      - It will accept a file using FastAPI's `UploadFile`.
      - It will perform security checks, allowing only specific file types (e.g., `.pdf`, `.txt`, `.md`, `.docx`).
      - It will use a document parser utility (`multiagent/utils/document_parser.py`) to extract text from the file.
      - It will then process the text:
        1.  **Chunking**: The extracted text will be split into smaller chunks using `RecursiveCharacterTextSplitter`.
        2.  **Embedding**: The text chunks will be converted into vector embeddings using the configured model (e.g., `OllamaEmbeddings` with `nomic-embed-text`).
        3.  **Ingestion**: The embeddings will be stored in a `Chroma` vector store at the session-specific path. If the store already exists, the new document will be added to it.

3.  **Update Database Model (Optional but Recommended)**:
    - To track which files have been uploaded to a session, the `UploadedFile` model in `app/database/models.py` can be simplified. It may only need to store a record that a file was added to a session's vector store, rather than its full path.
    - **Schema**: `id`, `filename`, `session_id`, `user_id`, `created_at`.

---

### **Phase 2: Multi-Agent System - Dynamic Context Retrieval**

With the document content indexed, the multi-agent system must be equipped to query the session's vector store. The agent-led approach provides the most flexibility and modularity.

1.  **Create a Session-Specific Retriever Utility**:

    - A new utility function or class will be created, for instance, in `multiagent/memory/manager.py` or a new `retriever_manager.py`.
    - This utility will have a function like `get_session_retriever(session_id: str, user_id: str)`.
    - **Functionality**:
      - It will construct the path to the session's vector store directory.
      - If the directory exists, it will initialize a `Chroma` vector store from the persisted data and return a retriever instance (`vector_store.as_retriever()`).
      - If it does not exist, it will return `None`.

2.  **Update Agent Logic for On-Demand RAG**:

    - Agents that can benefit from user-provided documents (e.g., an `ExamAgent`, `OBEAgent`, or a general-purpose `DocumentQueryAgent`) will be modified.
    - **Workflow**:
      1.  Inside the agent's main execution logic, it will first call `get_session_retriever()` using the `session_id` and `user_id` from the state.
      2.  If a retriever is available, the agent will use it to query for context relevant to the user's question. A `RetrievalQA` chain is ideal for this, as it combines the retriever with an LLM to synthesize an answer.
      3.  The agent can then use the retrieved context to answer the user's question, generate content, or perform its specialized task.
      4.  If no retriever is found, the agent proceeds with its standard workflow without the document context.

    ```python
    # Example modification in an agent
    from multiagent.memory import get_session_retriever
    from langchain.chains import RetrievalQA

    class ObeAgent:
        def answer(self, question: str, session_id: str, user_id: str):
            session_retriever = get_session_retriever(session_id, user_id)

            if session_retriever:
                # If a vector store exists for this session, use it
                qa_chain = RetrievalQA.from_chain_type(llm=self.llm, retriever=session_retriever)
                result = qa_chain.invoke(question)
                return result['result']
            else:
                # Fallback to default behavior
                return "No document has been uploaded for this session. Please upload a file first."
    ```

3.  **Supervisor Routing**:
    - The supervisor's role remains largely the same: route the user's question to the appropriate agent.
    - The supervisor does **not** need to manage the file context directly. It simply needs to ensure that the `session_id` and `user_id` are passed down through the state, so the agents can use them.
    - A new routing rule could be added to the supervisor classifier to detect when a query is explicitly about an "attached" or "uploaded" document, directing it to an agent capable of RAG.

---

### **Phase 4: Intelligent Agent Design and Workflow**

With the infrastructure in place, the focus shifts to making agents intelligent about how and when to use document context. Agents should not just blindly use retrieved information; they must be strategic.

1.  **Prompt-Driven Retrieval Logic**:

    - Agents must be designed to analyze the user's prompt to decide if document retrieval is necessary. The agent's internal prompt should instruct it to look for explicit cues (e.g., "in the attached file," "using the slides," "based on this document") or implicit needs (e.g., a request to "summarize the course outline" when a syllabus has been uploaded).

2.  **Multi-Step, Task-Oriented Retrieval**:

    - For complex queries, agents will employ a multi-step process instead of a single RAG call. This is crucial for tasks like the CLO-PLO mapping.
    - **Example Workflow (OBE Agent)**:
      1.  **Analyze Request**: User asks, "Generate the CLO-PLO mapping from the uploaded course outline."
      2.  **Step 1: Initial Extraction**: The agent first formulates a targeted query for the session retriever, such as: "Extract all Course Learning Outcomes (CLOs) and Program Learning Outcomes (PLOs) listed in this document."
      3.  **Step 2: Synthesize and Generate**: The agent takes the extracted CLOs and PLOs as structured input for its next reasoning step. It then uses its core logic to generate the mapping between them.
      4.  **Step 3: Present Result**: The final, structured mapping is returned to the user.

3.  **Agent Specialization and Contextual Awareness**:

    - Different agents will use the document context in specialized ways:
      - **OBE Agent**: Will be updated to first check if CLOs/PLOs are provided directly in the prompt. If not, it will query the session vector store to find them before attempting a mapping.
      - **Exam Agent**: When asked to generate questions or quizzes, it will use the session retriever to pull key topics, learning objectives, and content sections from uploaded documents to use as "inspiration," ensuring the questions are relevant to the provided material. For example, if a user uploads lecture slides and requests "generate a quiz from these slides," the agent will retrieve pertinent content from the slides to create targeted quiz questions. The current logic for getting inspiration from the exam bank we created will remain the same. If no document is uploaded, it will revert to its default behavior.
      - **New Personal Tutor Agent**: This new agent will be designed specifically for heavy RAG tasks. Given uploaded lecture slides or notes, it will perform multiple, targeted retrievals to generate a comprehensive study guide, including summaries, key concepts, potential exam questions, and flashcards.

4.  **Updating the Supervisor for New Capabilities**:
    - The supervisor's routing classifier will be updated to recognize prompts that imply heavy document interaction. For example, a query like "create a study guide from these slides" will be routed directly to the `Personal Tutor Agent`. This ensures that document-centric tasks are handled by the most appropriate specialist agent.

---

### **Phase 5: Frontend (HTML/JavaScript) - UI for File Uploads**

The frontend changes are minimal and focused on providing the upload mechanism.

1.  **Modify `app/static/index.html`**:
    - **UI Changes**:
      - Add a file input button (e.g., a paperclip icon 📎) to the chat interface.
      - Display the name of the selected file.
    - **JavaScript Logic**:
      - When the user clicks "send" with a file attached:
        1.  The JavaScript will first make a `POST` request to the `/api/v1/chats/{session_id}/upload` endpoint, sending the file data.
        2.  The backend will handle the ingestion and respond with a success message (e.g., `{"message": "File processed successfully"}`).
        3.  The frontend can then display a confirmation to the user (e.g., "Your file has been uploaded and is ready.").
        4.  The user can then ask questions about the document in subsequent messages. The original message sent with the file can be ignored or treated as a standard query. This decouples the upload action from the chat action.
