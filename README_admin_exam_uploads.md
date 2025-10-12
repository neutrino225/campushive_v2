# Implementation Plan: Admin Exam Uploads with Vector Store Integration

This document outlines the plan to add functionality for administrators to upload exam PDFs for specific courses. The uploaded exams will be processed, structured, saved to the filesystem, and integrated into the existing exam vector store for use by the Exam Agent and other components.

---

### **Phase 1: Backend (FastAPI) - Admin Exam Upload API**

The first step is to create a secure API endpoint that allows authenticated administrators to upload exam PDFs.

1.  **Authentication and Authorization**:

    - The endpoint will require JWT authentication and verify that the user has the `admin` role.
    - Use the existing `get_current_user` dependency from `app/auth/dependencies.py` and check `user.role == "admin"`.

2.  **Create a New API Endpoint**:

    - Add a new endpoint in `app/routers/admin.py` (or extend existing admin router): `POST /api/v1/admin/exams/upload`.
    - **Functionality**:

      - Accept a file upload using FastAPI's `UploadFile`.
      - Accept additional form data: `course_name` (string), `exam_type` (e.g., "Midterm", "Final").
      - Perform security checks: Allow only `.pdf` files, limit file size (e.g., 10MB), scan for malicious content if possible.
      - Generate a unique filename to avoid conflicts (e.g., `{course_name}_{exam_type}_{timestamp}.pdf`).
      - Save the file to `data/exams/{course_name}/` (create directory if it doesn't exist).
      - Create a database record in the `uploaded_exams` table with initial status "processing".
      - Return the upload ID for tracking.

    - Add another endpoint: `GET /api/v1/admin/exams/list` to retrieve uploaded exams.
    - **Functionality**:
      - Query the `uploaded_exams` table, join with `users` table to get uploader info.
      - Return paginated list of exams with status, upload date, course, etc.
      - Support filtering by status, course, date range.

3.  **File Processing Pipeline**:

    - After saving the file, trigger asynchronous processing (using FastAPI's background tasks or a task queue like Celery for production).
    - **Processing Steps**:
      1.  Extract text from the PDF using PyMuPDF (fitz).
      2.  Use `ExamAnalyzer` from `multiagent/parsers/exam_parser.py` to structure the exam into `StructuredExam` (course, exam_type, questions with text, marks, difficulty, topic).
      3.  Append the structured exam to `data/structured_exams.json` (load existing, append, save back).
      4.  Process the new exam into `Document` objects using logic similar to `ExamDataProcessor`.
      5.  Add the new documents to the existing `EXAMS` vector store using Chroma's `add_documents` method.
      6.  Update the database record status to "processed" or "failed" based on success.

4.  **Error Handling and Logging**:

    - Implement comprehensive error handling: PDF parsing failures, LLM analysis errors, file I/O issues.
    - Log all operations for auditing.
    - Return appropriate HTTP status codes and error messages (e.g., 400 for invalid file, 403 for unauthorized, 500 for processing errors).

5.  **Database Tracking (Required)**:
    - Extend the database model to track uploaded exams: Add `UploadedExam` table in `app/database/models.py` with fields like `id`, `filename`, `course_name`, `exam_type`, `uploaded_by` (user_id), `uploaded_at`, `status` (processed/failed), `file_path`.
    - Update the status after processing.
    - Create migration script to add the table to the database.
    - **Implementation Steps**:
      1. Add the `UploadedExam` model to `app/database/models.py`:
         ```python
         class UploadedExam(Base):
             __tablename__ = "uploaded_exams"

             id = Column(Integer, primary_key=True, index=True)
             filename = Column(String, nullable=False)
             course_name = Column(String, nullable=False)
             exam_type = Column(String, nullable=False)
             uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
             uploaded_at = Column(DateTime, default=datetime.utcnow)
             status = Column(String, default="processing")  # processing, processed, failed
             file_path = Column(String, nullable=False)

             # Relationship
             uploader = relationship("User", back_populates="uploaded_exams")
         ```
      2. Add relationship to `User` model:
         ```python
         class User(Base):
             # ... existing fields ...
             uploaded_exams = relationship("UploadedExam", back_populates="uploader")
         ```
      3. Create and run migration:

         ```bash
         # If using Alembic
         alembic revision --autogenerate -m "Add uploaded_exams table"
         alembic upgrade head

         # Or manually update the database schema
         python scripts/init_db.py  # If script supports migrations
         ```

---

### **Phase 2: Vector Store Integration**

Integrate the uploaded exam data into the existing exam vector store without recreating it from scratch.

1.  **Extend VectorStoreManager**:

    - Add a new method `add_documents_to_store(store_type: VectorStoreType, documents: List[Document])` in `vector_store_manager.py`.
    - **Functionality**:
      - Load the existing Chroma vector store for the given type.
      - If the store doesn't exist, create it first.
      - Split the documents using the configured text splitter.
      - Add the split documents to the store using `vector_store.add_documents(split_docs)`.
      - Persist the changes.

2.  **Document Processing for New Exams**:

    - Create a utility function to convert a `StructuredExam` into a list of `Document` objects, mirroring the logic in `ExamDataProcessor.process_data`.
    - Ensure metadata includes `source` with the filename, `course`, `exam_type`, etc.

3.  **Atomic Updates**:
    - Ensure that JSON file updates and vector store additions are atomic (use transactions or careful ordering).
    - If vector store addition fails, rollback JSON changes if possible.

---

### **Phase 3: Agent Integration**

Update the Exam Agent to leverage the expanded exam vector store.

1.  **Exam Agent Enhancements**:

    - The Exam Agent already uses the `EXAMS` vector store for generating questions.
    - With new uploads, the agent will have access to more diverse and up-to-date exam questions.
    - Ensure the retriever is refreshed or uses the latest data (Chroma handles persistence automatically).

2.  **Supervisor Routing**:
    - No changes needed; existing routing to Exam Agent will suffice.
    - Optionally, add keywords like "upload exam" but since this is admin-only, routing might not apply.

---

### **Phase 4: Frontend (Admin Interface) - Exam Upload UI**

Provide a user interface for administrators to upload exams.

1.  **Admin Dashboard**:

    - Create or extend an admin page in `app/static/admin.html` (separate from the main chat UI).
    - **UI Elements**:
      - File upload input for PDF files.
      - Form fields: Course name (dropdown or text), Exam type (dropdown: Midterm, Final, Sessional).
      - Upload button with progress indicator.
      - Display list of recently uploaded exams with status (fetched from `/api/v1/admin/exams/list` endpoint that queries the database).

2.  **JavaScript Logic**:

    - On upload, send a POST request to `/api/v1/admin/exams/upload` with the file and form data.
    - Include JWT token in Authorization header.
    - Handle responses: Show success message, update the list of exams.
    - Implement client-side validation (file type, size).

3.  **Integration with Main UI (Optional)**:
    - If keeping it simple, admins can use the main chat interface with a special command, but a dedicated admin UI is preferable for better UX.

---

### **Phase 5: Testing and Validation**

Ensure the pipeline is robust and reliable.

1.  **Unit Tests**:

    - Test PDF text extraction.
    - Test ExamAnalyzer with mock LLM responses.
    - Test VectorStoreManager.add_documents_to_store.
    - Test API endpoint with mock uploads.
    - Test database operations: creating UploadedExam records, updating status, querying exams list.

2.  **Integration Tests**:

    - End-to-end test: Upload PDF → Process → Query vector store → Verify results in Exam Agent.

3.  **Security Testing**:

    - Test unauthorized access attempts.
    - Test malicious file uploads.
    - Validate file size limits.

4.  **Performance Considerations**:
    - Process uploads asynchronously to avoid blocking the API.
    - Monitor vector store size; consider periodic cleanup or archiving old exams.

---

### **Key Considerations**

- **Data Consistency**: Ensure that `structured_exams.json` and the vector store remain in sync. If JSON update fails, don't add to vector store. Update database status accordingly.
- **Database Integrity**: The `uploaded_exams` table serves as the source of truth for tracking all admin uploads. Use transactions for atomic operations.
- **Scalability**: For large numbers of uploads, consider batch processing or a queue system.
- **Backup**: Regularly backup `data/exams/` directory, vector stores, and database.
- **Privacy**: Exams may contain sensitive information; ensure proper access controls.
- **Versioning**: If exams are updated, handle overwrites carefully (e.g., by filename or unique ID).

This pipeline provides a secure, efficient way for admins to expand the exam database, enhancing the system's ability to generate relevant questions and quizzes.</content>
<parameter name="filePath">/home/neutrino/projects/fyp_test/README_admin_exam_uploads.md
