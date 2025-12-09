import sys
from pathlib import Path

# Ensure project root is on sys.path for `from config import llm`
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import fitz  # PyMuPDF
import os
from pathlib import Path
from config import llm
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import List, Optional, Union

class Question(BaseModel):
    question_text: str = Field(description="The full text of the question")
    marks: Optional[Union[int, str]] = Field(default=None, description="Marks allocated to the question (integer preferred; may be string like '5' or '5 marks')")
    difficulty: Optional[str] = Field(default=None, description="Estimated difficulty (e.g., Easy, Medium, Hard)")
    topic: Optional[str] = Field(default=None, description="The primary topic of the question")

class StructuredExam(BaseModel):
    course: str = Field(description="The course name for the exam")
    exam_type: Optional[str] = Field(default="Unknown", description="The type of exam (e.g., Sessional, Final, Midterm, Quiz). Use 'Unknown' if not clearly stated.")
    questions: List[Question] = Field(description="A list of questions in the exam")

class ExamAnalyzer:
    def __init__(self):
        self.llm = llm
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an expert at analyzing exam papers. Your task is to extract structured information from the raw text of an exam. "
                    "Identify the course, exam type, and all the questions. For each question, extract the question text, marks, estimated difficulty, and topic. "
                    "If exam_type is not clearly stated in the document, use 'Unknown'. "
                    "For marks, prefer integers but accept strings if the format is unclear. Convert float marks (like 2.5) to integers by rounding. "
                    "Return the information in the specified JSON format. "
                    "Focus on extracting actual exam questions, not instructions or header information.",
                ),
                ("human", "Exam Text:\n{exam_text}\n\nCourse: {course_name}"),
            ]
        )
        self.structured_llm = self.prompt | self.llm.with_structured_output(StructuredExam)

    def analyze_exam(self, raw_text: str, course_name: str) -> Optional[StructuredExam]:
        """Analyzes raw exam text to extract structured data."""
        try:
            result = self.structured_llm.invoke({"exam_text": raw_text, "course_name": course_name})
            # Normalize marks: coerce strings like "5" or "5 marks" to int when possible
            # Also handle floats by rounding to nearest int
            for q in result.questions:
                if q.marks is not None:
                    if isinstance(q.marks, float):
                        q.marks = int(round(q.marks))
                    elif isinstance(q.marks, str):
                        import re
                        m = re.search(r"\d+\.?\d*", q.marks)
                        if m:
                            try:
                                q.marks = int(round(float(m.group(0))))
                            except Exception:
                                pass
            return result
        except Exception as e:
            print(f"Error analyzing exam for course {course_name}: {e}")
            return None

class ExamParser:
    def __init__(self, data_path: str):
        self.data_path = Path(data_path)

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extracts text from a single PDF file."""
        try:
            doc = fitz.open(pdf_path)
            try:
                text = "".join(page.get_text() for page in doc)
            finally:
                doc.close()
            # Normalize whitespace and limit size to keep LLM prompt reasonable
            text = text.replace("\x00", "").strip()
            if len(text) > 20000:
                text = text[:20000]
            return text
        except Exception as e:
            print(f"Error reading {pdf_path}: {e}")
            return ""

    def process_all_exams(self):
        """Processes all exam PDFs in the specified directory structure."""
        analyzer = ExamAnalyzer()
        structured_exams = []
        for course_dir in self.data_path.iterdir():
            if course_dir.is_dir():
                course_name = course_dir.name
                for exam_file in course_dir.glob("*.pdf"):
                    print(f"Processing {exam_file.name} in {course_name}...")
                    raw_text = self.extract_text_from_pdf(exam_file)
                    if raw_text:
                        structured_exam = analyzer.analyze_exam(raw_text, course_name)
                        if structured_exam:
                            structured_exams.append(structured_exam)
        return structured_exams

if __name__ == '__main__':
    # Example usage:
    # This assumes the script is run from the root of the project.
    exams_path = 'data/exams'
    parser = ExamParser(exams_path)
    structured_data = parser.process_all_exams()
    print(f"Successfully structured {len(structured_data)} exams.")
    # You can now save this structured_data to a JSON file or process it further
    import json
    with open('data/structured_exams.json', 'w') as f:
        json.dump([exam.model_dump() for exam in structured_data], f, indent=2)
