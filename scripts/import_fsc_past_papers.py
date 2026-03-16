#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.exams import analyze_pdf_to_structured
from vector_store_manager import VectorStoreManager, VectorStoreType
from config import embeddings


SOURCE_REPO_URL = "https://github.com/nuces-isb-past-papers/fsc-past-papers"
DEFAULT_SOURCE = Path("/tmp/fsc-past-papers-shallow")
DEFAULT_EXAMS_DIR = ROOT / "data" / "exams"
DEFAULT_STRUCTURED_PATH = ROOT / "data" / "structured_exams.json"


@dataclass(frozen=True)
class PaperRecord:
    source_pdf: Path
    semester: str
    course: str
    department: str
    exam_type: str
    relative_path: str


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", value).strip().lower()
    cleaned = re.sub(r"[-\s]+", "_", cleaned)
    return cleaned or "unknown"


def _normalize_label(value: str) -> str:
    value = value.replace("_", " ").replace("-", " ").strip()
    return re.sub(r"\s+", " ", value)


def _infer_exam_type(filename: str) -> str:
    lowered = filename.lower()
    patterns = [
        (r"final", "Final"),
        (r"mid\s*term|midterm|mid", "Midterm"),
        (r"sessional\s*[- ]*1|sessional\s*i\b|s1\b", "Sessional 1"),
        (r"sessional\s*[- ]*2|sessional\s*ii\b|s2\b", "Sessional 2"),
        (r"sessional", "Sessional"),
        (r"quiz", "Quiz"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, lowered):
            return label
    return "Unknown"


def _extract_record(pdf_path: Path, source_root: Path) -> PaperRecord | None:
    relative_parts = pdf_path.relative_to(source_root).parts
    if len(relative_parts) < 3:
        return None

    semester = _normalize_label(relative_parts[0])
    filename = pdf_path.name

    if len(relative_parts) >= 4:
        course = _normalize_label(relative_parts[1])
        department = _normalize_label(relative_parts[2])
    else:
        course = _normalize_label(relative_parts[1])
        department = "Unknown"

    return PaperRecord(
        source_pdf=pdf_path,
        semester=semester,
        course=course,
        department=department,
        exam_type=_infer_exam_type(filename),
        relative_path=str(pdf_path.relative_to(source_root)),
    )


def discover_papers(source_root: Path, limit: int | None = None) -> list[PaperRecord]:
    papers: list[PaperRecord] = []
    for pdf_path in sorted(source_root.rglob("*.pdf")):
        if "Course Outlines" in pdf_path.parts:
            continue
        record = _extract_record(pdf_path, source_root)
        if record is not None:
            papers.append(record)
            if limit is not None and len(papers) >= limit:
                break
    return papers


def copy_papers_to_exams_dir(papers: Iterable[PaperRecord], exams_dir: Path) -> list[tuple[PaperRecord, Path]]:
    copied: list[tuple[PaperRecord, Path]] = []
    for paper in papers:
        course_dir = exams_dir / paper.course
        course_dir.mkdir(parents=True, exist_ok=True)
        target_name = (
            f"{_slugify(paper.department)}__"
            f"{_slugify(paper.semester)}__"
            f"{paper.source_pdf.name}"
        )
        destination = course_dir / target_name
        if not destination.exists():
            shutil.copy2(paper.source_pdf, destination)
        copied.append((paper, destination))
    return copied


def build_structured_dataset(copied_papers: Iterable[tuple[PaperRecord, Path]]) -> list[dict]:
    structured_items: list[dict] = []

    for paper, local_pdf in copied_papers:
        structured = analyze_pdf_to_structured(str(local_pdf), paper.course)
        if structured is None:
            continue

        exam_dict = structured.dict()
        exam_dict["filename"] = local_pdf.name
        exam_dict["semester"] = paper.semester
        exam_dict["department"] = paper.department
        exam_dict["source_repo"] = SOURCE_REPO_URL
        exam_dict["source_path"] = paper.relative_path
        if not exam_dict.get("exam_type") or exam_dict["exam_type"] == "Unknown":
            exam_dict["exam_type"] = paper.exam_type

        structured_items.append(exam_dict)

    return structured_items


def write_structured_exams(structured_items: list[dict], structured_path: Path) -> None:
    structured_path.parent.mkdir(parents=True, exist_ok=True)
    structured_path.write_text(json.dumps(structured_items, indent=2), encoding="utf-8")


def rebuild_exam_store() -> None:
    manager = VectorStoreManager(embeddings=embeddings)
    manager.create_vector_store(VectorStoreType.EXAMS, force_recreate=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import FSC past papers into the CampusHive exam pipeline.")
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Path to a local clone/download of the FSC past papers repo.",
    )
    parser.add_argument(
        "--exams-dir",
        type=Path,
        default=DEFAULT_EXAMS_DIR,
        help="Target directory for raw exam PDFs used by the current pipeline.",
    )
    parser.add_argument(
        "--structured-path",
        type=Path,
        default=DEFAULT_STRUCTURED_PATH,
        help="Output path for structured_exams.json.",
    )
    parser.add_argument(
        "--rebuild-store",
        action="store_true",
        help="Rebuild the EXAMS vector store after importing.",
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Only copy PDFs into data/exams. Do not build structured_exams.json or vector store.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of PDFs to process.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = args.source.resolve()

    if not source_root.exists():
        print(
            f"Source repo not found at {source_root}. "
            f"Clone or download {SOURCE_REPO_URL} first.",
            file=sys.stderr,
        )
        return 1

    papers = discover_papers(source_root, limit=args.limit)
    if not papers:
        print(f"No PDF past papers found under {source_root}", file=sys.stderr)
        return 1

    copied = copy_papers_to_exams_dir(papers, args.exams_dir.resolve())
    structured_items: list[dict] = []
    if not args.skip_analysis:
        structured_items = build_structured_dataset(copied)
        write_structured_exams(structured_items, args.structured_path.resolve())

    if args.rebuild_store and not args.skip_analysis:
        rebuild_exam_store()

    print(f"Discovered {len(papers)} PDF papers")
    print(f"Copied {len(copied)} PDFs into {args.exams_dir}")
    if args.skip_analysis:
        print("Skipped structured exam analysis")
    else:
        print(f"Structured {len(structured_items)} exams into {args.structured_path}")
    if args.rebuild_store and not args.skip_analysis:
        print("Rebuilt EXAMS vector store")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
