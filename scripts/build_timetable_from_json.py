#!/usr/bin/env python3
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SOURCE_PATH = DATA_DIR / "timetable_source.json"
CSV_PATH = DATA_DIR / "structured_timetable.csv"
MAPPINGS_PATH = DATA_DIR / "mappings.json"


PROGRAM_CODES = {
    "BS CS": "CS",
    "BS AI": "AI",
    "BS SE": "SE",
    "BS DS": "DS",
    "BS CY": "CY",
}


DEFAULT_MAPPINGS = {
    "operating systems": "os",
    "operating system": "os",
    "operating systems lab": "os lab",
    "computer organization and assembly language": "coal",
    "computer organization & assembly language": "coal",
    "computer organization assembly language": "coal",
    "computer organization": "coal",
    "assembly language": "coal",
    "computer networks": "comp net",
    "networks": "comp net",
    "database systems": "db",
    "database": "db",
    "artificial intelligence": "ai",
    "probability and statistics": "prob & stats",
    "probability & statistics": "prob & stats",
    "multivariable calculus": "mv calculus",
    "multi variable calculus": "mv calculus",
    "oop": "oop",
    "object oriented programming": "oop",
    "data structures and algorithms": "sda",
    "software design and analysis": "sda",
    "parallel and distributed computing": "pdc",
    "information security": "info sec",
    "software engineering": "se",
    "deep learning": "deep learn",
    "computer vision": "comp vision",
    "natural language processing": "nlp",
    "computer science": "cs",
    "artificial intelligence program": "ai",
    "software engineering program": "se",
    "data science": "ds",
    "cyber security": "cy",
}


def build_rows(source: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for day, programs in source.items():
        for program, batches in programs.items():
            program_code = PROGRAM_CODES.get(program, program)
            for batch, sections in batches.items():
                for section, classes in sections.items():
                    for entry in classes:
                        name = str(entry.get("name", "")).strip()
                        room = str(entry.get("location", "")).strip()
                        time = str(entry.get("time", "")).strip()
                        if not name or not room or not time:
                            continue

                        rows.append(
                            {
                                "Class": f"{name} {program_code}-{section}",
                                "Course": name,
                                "Program": program,
                                "ProgramCode": program_code,
                                "Batch": str(batch),
                                "Section": section,
                                "Room": room,
                                "Time": time,
                                "Day": day,
                            }
                        )

    rows.sort(
        key=lambda row: (
            row["Day"],
            row["Program"],
            row["Batch"],
            row["Section"],
            row["Time"],
            row["Course"],
        )
    )
    return rows


def write_csv(rows: list[dict[str, str]]) -> None:
    fieldnames = ["Class", "Course", "Program", "ProgramCode", "Batch", "Section", "Room", "Time", "Day"]
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_mappings(rows: list[dict[str, str]]) -> dict[str, str]:
    mappings = dict(DEFAULT_MAPPINGS)

    for row in rows:
        course = row["Course"].lower()
        program = row["Program"].lower()
        program_code = row["ProgramCode"].lower()
        section = row["Section"].lower()
        class_name = row["Class"].lower()

        mappings[f"{course} {program_code} {section}"] = class_name
        mappings[f"{course} {program_code}-{section}"] = class_name
        mappings[f"{course} {program} {section}"] = class_name
        mappings[f"{course} section {section}"] = f"{course} {program_code} {section}"
        mappings[f"{course} {section}"] = f"{course} {program_code} {section}"

    return dict(sorted(mappings.items()))


def main() -> None:
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    rows = build_rows(source)
    write_csv(rows)
    mappings = build_mappings(rows)
    MAPPINGS_PATH.write_text(json.dumps(mappings, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} timetable rows to {CSV_PATH}")
    print(f"Wrote {len(mappings)} mappings to {MAPPINGS_PATH}")


if __name__ == "__main__":
    main()
