import os
import json
from pathlib import Path
import sys

# Ensure project root is on sys.path for package imports
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from multiagent.parsers.exam_parser import ExamParser, ExamAnalyzer
DATA_DIR = ROOT / "data"
EXAMS_DIR = DATA_DIR / "exams"
STRUCTURED_PATH = DATA_DIR / "structured_exams.json"


def build_structured_exams(limit_per_course: int | None = None) -> int:
    parser = ExamParser(str(EXAMS_DIR))
    analyzer = ExamAnalyzer()

    count = 0
    structured = []

    for course_dir in sorted(EXAMS_DIR.iterdir()):
        if not course_dir.is_dir():
            continue
        course_name = course_dir.name
        seen = 0
        for pdf in sorted(course_dir.glob("*.pdf")):
            try:
                raw_text = parser.extract_text_from_pdf(pdf)
                if not raw_text:
                    continue
                exam = analyzer.analyze_exam(raw_text, course_name)
                if exam:
                    # attach filename for traceability
                    d = exam.model_dump()
                    d["filename"] = pdf.name
                    structured.append(d)
                    count += 1
                    seen += 1
                    if limit_per_course and seen >= limit_per_course:
                        break
            except Exception as e:
                print(f"Skipping {pdf.name}: {e}")
                continue

    STRUCTURED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STRUCTURED_PATH, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2)

    return count


if __name__ == "__main__":
    n = build_structured_exams()
    print(f"Structured {n} exam files -> {STRUCTURED_PATH}")
