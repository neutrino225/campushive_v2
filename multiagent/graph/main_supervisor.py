import sys
from pathlib import Path
from typing import List, Optional

# Add project root to path
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langgraph.graph import StateGraph, END
from langgraph.types import Command
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from config import llm
from multiagent.memory import memory_manager
import re


# Keep state compatible with existing system
try:
    from typing_extensions import TypedDict
except ImportError:
    from typing import TypedDict  # type: ignore


class MainState(TypedDict):
    question: str
    result: str
    route: List[str]
    session_id: str
    conversation_history: List
    user_role: str
    messages: List


def _is_small_talk(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if re.search(r"\b(hi|hello|hey|howdy|salam|assalam(?:ualaikum)?)\b", t):
        return True
    if re.search(r"\b(thanks?|thank\s+you|appreciate(?:\s+it)?)\b", t):
        return True
    if t in {"ok", "okay", "sure", "alright", "sounds good"}:
        return True
    if re.search(r"\b(bye|goodbye|see you|later)\b", t):
        return True
    return False


def _looks_like_followup_pronoun(text: str) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    # Short follow-up or contains pronouns
    if len(t.split()) <= 8 and re.search(r"\b(it|that|this|those|them|they|their|his|her|him)\b", t):
        return True
    if t.startswith("and ") or t.startswith("also "):
        return True
    return False


def _prior_domain_from_history(session_id: str) -> Optional[str]:
    hist = memory_manager.get_history(session_id) or []
    for turn in reversed(hist):
        for step in reversed(turn.route or []):
            if "faculty" in step:
                return "faculty"
            if "student" in step:
                return "student"
            if "exam" in step:
                return "exam"
    return None


def create_main_supervisor_node():
    """LLM router that picks domain: student_supervisor, faculty, exam, direct."""
    system_prompt = (
        "You are the MAIN supervisor router. Decide which domain should handle the user's question.\n"
        "You have access to recent conversation history. Use it to understand context and follow-up questions.\n"
        "Return EXACTLY one of: student, faculty, exam, direct\n\n"
        "Domain descriptions:\n"
        "- student: Degree programs, admissions, courses, timetables, academic policies, campus facilities\n"
        "- faculty: Faculty directory, professor info, contact details, research areas\n"
        "- exam: Exam generation (for faculty/admin only)\n"
        "- direct: Greetings, small talk, meta questions\n\n"
        "Examples:\n"
        "Q: 'Who is my academic advisor?'\nA: student\n"
        "Q: 'What courses are in semester 3?' (after discussing BS AI)\nA: student\n"
        "Q: 'Map CLO1 to PLO2'\nA: faculty\n"
        "Q: 'Generate exam for CS101'\nA: exam\n"
        "Q: 'Hello'\nA: direct\n"
    )

    async def node(state: MainState):
        q = state.get("question", "")
        session_id = state.get("session_id", "default")
        
        # Include conversation context for better routing decisions
        context = memory_manager.get_last_context(session_id, last_n=5)
        question_with_context = f"{context}\n{q}" if context else q
        
        msgs = [SystemMessage(content=system_prompt), HumanMessage(content=f"Question: {question_with_context}")]
        # Heuristic pre-routing: keep 'direct' only for true small talk
        decision: Optional[str] = None
        if _is_small_talk(q):
            decision = "direct"
        else:
            # Hard keyword heuristics for robust domain selection
            ql = q.lower()
            # Leadership/admin facts are generally stored in general university docs
            # (student domain), not faculty directory profiles.
            if any(k in ql for k in [
                "rector", "vice chancellor", "vice-chancellor", "registrar",
                "controller of examinations", "controller examinations"
            ]):
                decision = "student"
            if any(k in ql for k in [
                "exam", "quiz", "test", "paper", "assessment"
            ]) and any(v in ql for v in [
                "generate", "create", "make", "build", "design", "draft", "prepare"
            ]):  # Route to exam when user asks to create/generate assessments
                decision = "exam"
            elif any(k in ql for k in [
                "professor", "prof ", "prof.", "dr.", "faculty member", "lecturer", "instructor",
                "head of", "chairman", "chair ", "hod", "school of computing"
            ]):
                decision = "faculty"
            # Check for student domain keywords
            elif any(k in ql for k in [
                "degree", "program", "course", "semester", "admission", "requirement",
                "credit", "timetable", "schedule", "enroll", "bs ", "ms ", "phd"
            ]):
                decision = "student"
            # If follow-up with pronoun, check prior domain
            elif _looks_like_followup_pronoun(q):
                prior = _prior_domain_from_history(state.get("session_id", "default"))
                if prior:
                    decision = prior
        
        # Use LLM if no heuristic match
        if not decision:
            try:
                resp = await llm.ainvoke(msgs)
                decision = (resp.content or "").strip().lower()
            except Exception:
                decision = "student"

        if decision not in {"student", "faculty", "exam", "direct"}:
            decision = "student"

        # Map decision to graph node names
        goto_node = "student_supervisor" if decision == "student" else decision

        updated_route = state.get("route", []) + [f"main:routed_to:{goto_node}"]
        debug_msg = f"[MAIN] Routing decision => {goto_node} (from: {q[:80]})"
        print(debug_msg)

        return Command(
            goto=goto_node,
            update={
                **state,
                "route": updated_route,
                "messages": state.get("messages", []) + [AIMessage(content=debug_msg, name="main_supervisor")],
            },
        )

    return node


def build_main_graph(student_supervisor_node, faculty_node, exam_node, direct_node):
    """Wire domain supervisors and leaf nodes into a top-level graph."""
    graph = StateGraph(MainState)

    graph.add_node("main_supervisor", create_main_supervisor_node())

    # Domain supervisors / leafs
    graph.add_node("student_supervisor", student_supervisor_node)
    graph.add_node("faculty", faculty_node)
    graph.add_node("exam", exam_node)
    graph.add_node("direct", direct_node)

    graph.set_entry_point("main_supervisor")

    # Domain and leaf exit to END
    graph.add_edge("student_supervisor", END)
    graph.add_edge("faculty", END)
    graph.add_edge("exam", END)
    graph.add_edge("direct", END)

    return graph.compile()
