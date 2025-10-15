# File Upload Feature - Quick Reference

## What Was Built

A complete backend system for uploading documents to chat sessions with automatic vector store integration for RAG.

## Quick Usage

### Upload a File (Python)

```python
import requests

# Login
response = requests.post("http://localhost:8000/api/v1/auth/login",
    json={"username": "student", "password": "pass"})
token = response.json()["access_token"]

# Upload to session
with open("notes.pdf", "rb") as f:
    response = requests.post(
        f"http://localhost:8000/api/v1/chats/42/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": f}
    )
print(response.json())
```

### Check if Session Has Documents

```python
from multiagent.memory.retriever_manager import has_session_documents

if has_session_documents(user_id=1, session_id="42"):
    print("Session has uploaded documents")
```

### Get Session Retriever in Agent

```python
from multiagent.memory.retriever_manager import get_session_retriever

retriever = get_session_retriever(user_id=1, session_id="42")
if retriever:
    # Use retriever for RAG
    results = retriever.get_relevant_documents("What is polymorphism?")
```

## API Endpoint

**POST** `/api/v1/chats/{session_id}/upload`

**Headers:**

- `Authorization: Bearer <token>`

**Body:**

- `file`: Document file (multipart/form-data, max 10 MB)

**Supported Formats:**

- `.txt` - Plain text
- `.md` - Markdown
- `.pdf` - PDF documents
- `.doc` / `.docx` - Word documents

**Security:**

- File size limit: 10 MB maximum
- MIME type validation
- Extension validation
- JWT authentication required

**Response:**

```json
{
	"status": "success",
	"filename": "notes.pdf",
	"chunks_created": 42
}
```

## Files Created

1. **`multiagent/utils/document_parser.py`**

   - Extracts text from various file formats
   - Functions: `parse_document()`, `is_supported_file()`, `get_supported_extensions()`

2. **`multiagent/memory/retriever_manager.py`**

   - Manages session-specific vector stores
   - Functions: `get_session_retriever()`, `has_session_documents()`
   - Class: `SessionRetrieverManager`

3. **Upload endpoint in `app/routers/chats.py`**
   - POST `/api/v1/chats/{session_id}/upload`
   - Validates, parses, chunks, embeds, and stores documents

## Storage Location

```
data/vector_stores/user_uploads/user_{user_id}_session_{session_id}/
```

Each user-session pair gets isolated vector store.

## Agent Integration Pattern

```python
def my_agent(question, session_id, user_id):
    retriever = get_session_retriever(user_id, session_id)

    if retriever:
        # Use uploaded documents
        from langchain.chains import RetrievalQA
        from config import llm
        qa = RetrievalQA.from_chain_type(llm, retriever=retriever)
        return qa.invoke({"query": question})["result"]
    else:
        # Fallback behavior
        return "No documents uploaded"
```

## Testing

### Quick Test

```bash
# Activate environment
conda activate fyp

# Start server
uvicorn app.main:app --reload

# In another terminal, test upload
curl -X POST http://localhost:8000/api/v1/chats/1/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@test.pdf"
```

### Run Tests (when written)

```bash
pytest tests/api_tests/test_file_upload.py
pytest tests/agent_tests/test_document_parser.py
pytest tests/agent_tests/test_retriever_manager.py
```

## Dependencies

**Required:**

- `langchain-community` (Chroma)
- `langchain-text-splitters`

**Optional (for full functionality):**

- `PyPDF2` - PDF parsing
- `python-docx` - Word document parsing

**Install:**

```bash
pip install PyPDF2 python-docx
# or
conda install pypdf2 python-docx
```

## Status

✅ **Backend Complete**

- Document parser
- Session retriever manager
- Upload API endpoint
- Vector store management

⏳ **Pending**

- Database model for tracking uploads
- Frontend UI integration
- Agent RAG enhancements
- Test cases

## Next Steps

1. **Add Database Model** (Optional)

   ```python
   class UploadedFile(Base):
       id = Column(Integer, primary_key=True)
       filename = Column(String, nullable=False)
       session_id = Column(Integer, ForeignKey("chat_sessions.id"))
       user_id = Column(Integer, ForeignKey("users.id"))
       created_at = Column(DateTime, default=datetime.utcnow)
   ```

2. **Update Frontend UI**

   - Add file input button (📎)
   - Show upload progress
   - Display success message

3. **Enhance Agents**

   - OBE Agent: Extract CLOs from syllabus
   - Exam Agent: Generate quiz from slides
   - Create Personal Tutor Agent

4. **Write Tests**
   - Unit tests for parser
   - Integration tests for upload flow
   - Agent RAG tests

## Common Issues

**Q: Import errors for PyPDF2/docx?**  
A: Expected - install optional dependencies: `pip install PyPDF2 python-docx`

**Q: Upload succeeds but no results?**  
A: Check if file was parsed correctly, verify chunks created, check embeddings working

**Q: How to delete uploaded files?**  
A: Currently deletes with session. Future: Add delete endpoint for individual files.

**Q: Can users share documents?**  
A: No - each user-session isolated. Future: Add sharing feature.

## Documentation

- Full Technical Guide: `README/README_file_upload_implementation.md`
- User Requirements: `README_file_uploads.md`
- Vector Store System: `README/README_vector_store_management.md`

---

**Quick Start:** Upload file → System chunks → Embeds → Stores → Agents retrieve → Context-aware answers ✨
