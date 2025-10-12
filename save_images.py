"""Utility script to export graph images for all available agents and list faculty tools.

Outputs (into ./images):
  - supervisor_graph.png
  - student_graph.png
  - faculty_graph.png
  - timetable_graph.png (if timetable resources load)
  - faculty_tools.md (listing structured faculty tools + descriptions)

Why a separate faculty tools file?
The faculty agent is a lightweight wrapper (not a LangGraph ReAct agent) so its internal
@tool functions do not appear as graph nodes. This file enumerates them explicitly.
"""
from __future__ import annotations
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Callable


def find_project_root(start_path: Path | None = None) -> Path:
    if start_path is None:
        start_path = Path(__file__).resolve().parent
    markers = ["run_assistant.py", "app", ".git", "README.md", "README"]
    cur = start_path
    for _ in range(8):
        for m in markers:
            if (cur / m).exists():
                return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path(__file__).resolve().parent


PROJECT_ROOT = find_project_root()
sys.path.insert(0, str(PROJECT_ROOT))

IMAGES_DIR = PROJECT_ROOT / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def _write_png(graph_obj: Any, out_path: Path, label: str) -> bool:
    try:
        g = graph_obj.get_graph(xray=True)
        png_bytes = g.draw_mermaid_png()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(png_bytes)
        print(f"[OK] Saved {label} -> {out_path.relative_to(PROJECT_ROOT)}")
        return True
    except Exception as e:
        print(f"[FAIL] {label}: {e}")
        traceback.print_exc()
        return False


def export_supervisor() -> bool:
    try:
        from multiagent.graph.supervisor import supervisor_graph
        return _write_png(supervisor_graph, IMAGES_DIR / "supervisor_graph.png", "supervisor graph")
    except Exception as e:
        print(f"[FAIL] supervisor import: {e}")
        return False


def export_student() -> bool:
    try:
        from multiagent.nodes.student import student_router_node
        return _write_png(student_router_node, IMAGES_DIR / "student_graph.png", "student graph")
    except Exception as e:
        print(f"[FAIL] student graph: {e}")
        return False


def export_faculty() -> bool:
    try:
        from multiagent.nodes.faculty import faculty_router_node
        return _write_png(faculty_router_node, IMAGES_DIR / "faculty_graph.png", "faculty graph")
    except Exception as e:
        print(f"[FAIL] faculty graph: {e}")
        return False


def export_faculty_react() -> bool:
    try:
        from multiagent.agents.faculty_react_agent import faculty_react_graph
        return _write_png(faculty_react_graph, IMAGES_DIR / "faculty_react_graph.png", "faculty react graph")
    except Exception as e:
        print(f"[FAIL] faculty react graph: {e}")
        return False


def export_timetable() -> bool:
    try:
        from multiagent.agents.timetable_agent import TimetableAgentBuilder
        builder = TimetableAgentBuilder(
            timetable_path=str(PROJECT_ROOT / "data" / "structured_timetable.csv"),
            mapping_path=str(PROJECT_ROOT / "data" / "mappings.json"),
        )
        agent = builder.get_agent()
        return _write_png(agent, IMAGES_DIR / "timetable_graph.png", "timetable graph")
    except FileNotFoundError as e:
        print(f"[WARN] Timetable data missing: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] timetable graph: {e}")
        return False


def export_exam() -> bool:
    try:
        from multiagent.graph.supervisor import supervisor_graph
        return _write_png(supervisor_graph, IMAGES_DIR / "exam_graph.png", "exam graph")
    except Exception as e:
        print(f"[FAIL] exam graph: {e}")
        return False


def main():
    print("Exporting graphs and faculty tools...\n")
    results: Dict[str, bool] = {}
    results["supervisor"] = export_supervisor()
    results["student"] = export_student()
    results["faculty"] = export_faculty()
    results["timetable"] = export_timetable()
    results["faculty_react"] = export_faculty_react()
    results["exam"] = export_exam()

    print("\nSummary:")
    for k, v in results.items():
        print(f" - {k}: {'OK' if v else 'FAILED'}")
    print("\nDone.")


if __name__ == "__main__":
    main()
