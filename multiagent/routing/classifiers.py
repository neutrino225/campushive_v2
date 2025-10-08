import re
from typing import Literal
from functools import lru_cache

# In-memory cache for questions (keyed by question string)
_supervisor_cache = {}
_student_cache = {}
_faculty_cache = {}

def _validate_label(label: str, allowed: set[str]) -> str:
    """Validate and sanitize the LLM output; return None if invalid."""
    label = label.strip().lower()
    if label in allowed:
        return label
    return None  # Indicates fallback

def classify_supervisor(question: str, llm) -> Literal["student", "faculty", "direct"]:
    """Classify for supervisor routing with LLM and keyword fallback."""
    if question in _supervisor_cache:
        return _supervisor_cache[question]
    
    prompt = (
        "You are a university assistant router. Classify the user's question into exactly one category:\n"
        "- 'student': Questions about university information, academics, campus facilities, policies, admissions, courses, degrees, programs, schedules, library, cafeteria, sports, clubs, events, or any university-related services\n"
        "- 'faculty': Questions about specific professors, lecturers, department heads, faculty contact information, or academic staff\n"
        "- 'direct': Simple greetings, thanks, basic conversation, or questions that don't require university-specific information\n"
        "\n"
        "Examples:\n"
        "- 'What time does the library open?' -> student (library is a university facility)\n"
        "- 'Who is the head of computer science?' -> faculty\n"
        "- 'Hello, how are you?' -> direct\n"
        "- 'What are the admission requirements?' -> student\n"
        "\n"
        "Question: {question}\n"
        "Output exactly one label: student, faculty, or direct. No explanation."
    ).format(question=question)
    
    try:
        response = llm.invoke(prompt).content.strip()
        label = _validate_label(response, {"student", "faculty", "direct"})
        if label:
            _supervisor_cache[question] = label
            return label
    except Exception:
        pass  # Fallback to keyword heuristic
    
    # Keyword-based fallback routing
    q = question.lower()
    
    # Check for direct/greeting responses
    if any(greeting in q for greeting in ["hi", "hello", "hey", "salam", "assalam", "thanks", "thank you"]):
        return "direct"
    
    # Leadership/administration roles should go to general university info (student path)
    if any(keyword in q for keyword in [
        "rector", "vice chancellor", "vice-chancellor", "vc", "registrar", "chancellor",
        "controller of examinations", "controller examinations"
    ]):
        return "student"

    # Check for faculty-related keywords
    if any(keyword in q for keyword in ["professor", "prof", "dr", "faculty", "head", "teacher", "instructor", "staff", "department head"]):
        return "faculty"
    
    # Check for university/student-related keywords (broad category)
    if any(keyword in q for keyword in ["university", "campus", "library", "admission", "degree", "course", "schedule", "fee", "policy", "program", "programme"]):
        return "student"
    
    # Default to student for general university queries
    return "student"

def classify_student(question: str, llm) -> Literal["general", "degree", "timetable"]:
    """Classify for student routing with LLM and keyword fallback."""
    if question in _student_cache:
        return _student_cache[question]
    
    prompt = (
        "You are a router for student queries. Classify the question into exactly one category:\n"
        "- 'general': General university information, campus facilities, policies, admissions, library, cafeteria, sports, clubs, events\n"
        "- 'degree': Questions about degree programs, courses, academic requirements, majors, minors\n"
        "- 'timetable': Questions about class schedules, course timings, room locations, when classes are held\n"
        "\n"
        "Output exactly one label: general, degree, or timetable. No explanation.\n"
        "Question: {question}"
    ).format(question=question)
    
    try:
        response = llm.invoke(prompt).content.strip()
        label = _validate_label(response, {"general", "degree", "timetable"})
        if label:
            _student_cache[question] = label
            return label
    except Exception:
        pass  # Fallback to keyword heuristic
    
    # Fallback: Use keyword heuristic
    q = question.lower()
    # Leadership/administration queries are general info
    if any(keyword in q for keyword in [
        "rector", "vice chancellor", "vice-chancellor", "vc", "registrar", "chancellor",
        "controller of examinations", "controller examinations"
    ]):
        return "general"
    if any(keyword in q for keyword in ["timetable", "schedule", "time", "class", "room", "when", "timing", "lecture"]):
        return "timetable"
    # Existing logic for degree
    if any(keyword in q for keyword in ["degree", "program", "course", "major", "minor", "requirement", "curriculum"]):
        return "degree"
    return "general"  # Default

def classify_faculty(question: str, llm) -> Literal["faculty_info"]:
    """Classify for faculty routing - all faculty questions go to faculty_info since placeholder removed."""
    if question in _faculty_cache:
        return _faculty_cache[question]
    
    # All faculty questions now go to faculty_info since we removed placeholders
    _faculty_cache[question] = "faculty_info"
    return "faculty_info"