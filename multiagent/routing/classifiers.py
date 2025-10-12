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

def classify_supervisor(question: str, llm, conversation_context: str = "") -> Literal["student", "faculty", "direct", "exam"]:
    """Classify for supervisor routing with LLM, considering conversation context.
    
    Args:
        question: The user's question
        llm: The language model to use for classification
        conversation_context: Recent conversation history for context-aware routing
    """
    
    prompt = (
        "You are a university assistant router. Classify the user's question into exactly one category:\n"
        "- 'student': Questions requiring NEW information about university, academics, campus facilities, policies, admissions, courses, degrees, programs, schedules, etc.\n"
        "- 'faculty': Questions requiring NEW information about specific professors, lecturers, department heads, academic staff, OR educational outcome mapping (CLO/PLO mapping)\n"
        "- 'exam': Questions related to generating exams, quizzes, or practice papers.\n"
        "- 'direct': Questions that can be answered using EXISTING conversation context (greetings, thanks, follow-ups, reformatting, clarifications)\n"
        "\n"
        "IMPORTANT: If there is relevant conversation context and the question is a follow-up, clarification, or reformatting request, choose 'direct'.\n"
        "IMPORTANT: Questions about CLO (Course Learning Outcomes) or PLO (Program Learning Outcomes) mapping should be routed to 'faculty'.\n"
        "\n"
        "Examples:\n"
        "- 'What time does the library open?' -> student (needs new information)\n"
        "- 'Who is the head of computer science?' -> faculty (needs new information)\n"
        "- 'Map CLOs to PLOs' -> faculty (outcome mapping)\n"
        "- 'Can you help with CLO-PLO alignment?' -> faculty (outcome mapping)\n"
        "- 'Generate a final exam for Computer Networks' -> exam\n"
        "- 'Create a quiz for me' -> exam\n"
        "- 'Hello, how are you?' -> direct (greeting)\n"
        "- 'Thanks!' -> direct (acknowledgment)\n"
        "- 'Put that in a table format' -> direct (reformatting existing information)\n"
        "- 'Can you explain that more?' -> direct (clarification of existing information)\n"
        "- 'What was my last question?' -> direct (memory query)\n"
        "\n"
    )
    
    if conversation_context:
        prompt += f"Recent conversation:\n{conversation_context}\n\n"
    
    prompt += f"Question: {question}\nOutput exactly one label: student, faculty, direct, or exam. No explanation."
    
    try:
        response = llm.invoke(prompt).content.strip()
        label = _validate_label(response, {"student", "faculty", "direct", "exam"})
        if label:
            return label
    except Exception:
        pass  # Fallback to keyword heuristic
    
    # Minimal keyword-based fallback (only for obvious cases)
    q = question.lower()

    if any(keyword in q for keyword in ["exam", "quiz", "test", "paper", "assessment"]):
        return "exam"
    
    # Greetings and thanks
    if any(greeting in q for greeting in ["hi", "hello", "hey", "salam", "assalam", "thanks", "thank you"]):
        return "direct"
    
    # OBE/CLO-PLO mapping keywords
    if any(keyword in q for keyword in ["clo", "plo", "course learning outcome", "program learning outcome", 
                                         "outcome mapping", "map outcome", "align outcome", "alignment"]):
        return "faculty"
    
    # Faculty keywords
    if any(keyword in q for keyword in ["professor", "prof", "dr.", "faculty member", "department head", "lecturer", "instructor"]):
        return "faculty"
    
    # Default to student for university-related queries
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