from __future__ import annotations
import os
from typing import List, Optional

import fitz  # PyMuPDF
from langchain_core.documents import Document

# Reuse analyzer and models from the existing parser module
from multiagent.parsers.exam_parser import ExamAnalyzer, StructuredExam


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract plain text from a PDF using PyMuPDF."""
    try:
        doc = fitz.open(pdf_path)
        try:
            text = "".join(page.get_text() for page in doc)
        finally:
            doc.close()
        # Normalize
        text = text.replace("\x00", "").strip()
        # Keep prompt size reasonable for LLM
        if len(text) > 20000:
            text = text[:20000]
        return text
    except Exception:
        return ""


def analyze_pdf_to_structured(pdf_path: str, course_name: str) -> Optional[StructuredExam]:
    """Analyze a PDF to a StructuredExam using the ExamAnalyzer LLM pipeline."""
    raw_text = extract_text_from_pdf(pdf_path)
    if not raw_text:
        return None
    analyzer = ExamAnalyzer()
    return analyzer.analyze_exam(raw_text, course_name)


def structured_exam_to_documents(structured: StructuredExam, source_filename: str) -> List[Document]:
    """Convert a StructuredExam to a list of LangChain Documents."""
    docs: List[Document] = []
    for q in structured.questions:
        content = (
            f"Course: {structured.course}\n"
            f"Exam Type: {structured.exam_type}\n"
            f"Topic: {q.topic or 'N/A'}\n"
            f"Question: {q.question_text}\n"
            f"Marks: {q.marks if q.marks is not None else 'N/A'}"
        )
        # ChromaDB only accepts str, int, float, or bool - no None values
        metadata = {
            "source": f"exam:{structured.course}:{os.path.basename(source_filename)}",
            "course": structured.course,
            "exam_type": structured.exam_type,
        }
        # Only add non-None values to metadata
        if q.topic is not None:
            metadata["topic"] = str(q.topic)
        if q.difficulty is not None:
            metadata["difficulty"] = str(q.difficulty)
        if q.marks is not None:
            metadata["marks"] = q.marks if isinstance(q.marks, (int, float)) else str(q.marks)
        
        docs.append(Document(page_content=content, metadata=metadata))
    return docs


def append_structured_exam_to_json(structured: StructuredExam, json_path: str) -> None:
    """Append a StructuredExam to the structured_exams.json file, creating if missing."""
    import json
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
            if not isinstance(existing, list):
                existing = []
    except Exception:
        existing = []
    existing.append(structured.model_dump())
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
