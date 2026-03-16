import sys
from pathlib import Path
from typing import List

root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langgraph.graph import StateGraph, END
from langgraph.types import Command
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from config import llm

try:
    from typing_extensions import TypedDict
except ImportError:
    from typing import TypedDict  # type: ignore


class StudentState(TypedDict):
    question: str
    result: str
    route: List[str]
    session_id: str
    conversation_history: List
    user_role: str
    messages: List


def create_student_supervisor_node():
    """Route inside student domain: general_info, timetable, degree_advisor."""
    system_prompt = (
        "You are the STUDENT domain supervisor for FAST-NUCES Islamabad. Route questions to the appropriate subagent.\n"
        "You have access to recent conversation history. Use it to understand context and references.\n"
        "Return EXACTLY one of: general_info, timetable, degree_advisor\n\n"
        "**Agent Responsibilities:**\n\n"
        "**general_info** (General university information):\n"
        "- Admission requirements & eligibility criteria\n"
        "- Admission process, test dates, application steps\n"
        "- Campus facilities, locations, contact info\n"
        "- Academic policies, fee structure\n"
        "- Scholarships and financial aid\n"
        "- General university questions\n\n"
        "**degree_advisor** (Degree program-specific information ONLY):\n"
        "- Specific degree program details (BS CS, BS AI, etc.)\n"
        "- Semester-wise course lists for a specific program\n"
        "- Program comparison (BS CS vs BS AI)\n"
        "- Career opportunities for a specific program\n"
        "- Helping students choose/recommend a degree program\n"
        "- Program vision, mission, educational objectives\n\n"
        "**timetable** (Class schedules):\n"
        "- Student timetables and class schedules\n"
        "- Section timings\n\n"
        "**CRITICAL RULES:**\n"
        "- Questions about 'admission requirements' or 'eligibility' = general_info\n"
        "- Questions about 'admission process' or 'how to apply' = general_info\n"
        "- Questions about a SPECIFIC degree program (BS AI, BS CS, etc.) = degree_advisor\n"
        "- Questions about 'semester courses' or 'course list' = degree_advisor (ONLY if a specific program is mentioned or clear from context)\n"
        "- If no specific program is mentioned, general university info = general_info\n\n"
        "Examples:\n"
        "Q: 'What are the admission requirements for BS programs?'\nA: general_info\n"
        "Q: 'What is the admission process at FAST?'\nA: general_info\n"
        "Q: 'Eligibility criteria for BS programs'\nA: general_info\n"
        "Q: 'What are the requirements for BS in AI?' (first mention)\nA: degree_advisor\n"
        "Q: 'Provide semester-wise course list' (after discussing BS AI)\nA: degree_advisor\n"
        "Q: 'Compare BS CS and BS AI'\nA: degree_advisor\n"
        "Q: 'Show me my timetable for Monday'\nA: timetable\n"
        "Q: 'When does admission open?'\nA: general_info\n"
        "Q: 'Tell me about campus facilities'\nA: general_info\n"
    )

    async def node(state: StudentState):
        from multiagent.memory import memory_manager
        
        q = state.get("question", "")
        session_id = state.get("session_id", "default")
        ql = q.lower()
        timetable_keywords = [
            "timetable",
            "class schedule",
            "section timing",
            "my schedule",
            "course schedule",
            "weekly schedule",
            "weekly timetable",
        ]
        day_keywords = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "today"]

        # Timetable queries need deterministic routing because the timetable
        # dataset is independent from the general/faculty vector stores.
        if any(k in ql for k in timetable_keywords) or (
            any(day in ql for day in day_keywords)
            and any(term in ql for term in ["schedule", "class", "classes", "course", "lecture", "timetable"])
        ):
            decision = "timetable"
        else:
            decision = None
        
        # Include conversation context for intelligent routing
        context = memory_manager.get_last_context(session_id, last_n=5)
        question_with_context = f"{context}\n{q}" if context else q
        
        if decision is None:
            msgs = [SystemMessage(content=system_prompt), HumanMessage(content=f"Question: {question_with_context}")]
            try:
                resp = await llm.ainvoke(msgs)
                decision = (resp.content or "").strip().lower()
            except Exception:
                # Improved fallback heuristics
                # Degree advisor keywords (program-specific queries)
                if any(k in ql for k in [
                    "bs cs", "bs ai", "bs se", "bs ee", "bs ce",  # Specific programs
                    "bachelor of science", "degree program",
                    "compare programs", "semester course", "course list",
                    "recommend degree", "choose program", "which program"
                ]):
                    decision = "degree_advisor"
                
                # General info keywords (admission, eligibility, university info)
                elif any(k in ql for k in [
                    "admission", "eligibility", "apply", "requirement",
                    "how to apply", "admission process", "admission test",
                    "campus", "facilities", "scholarship", "fee",
                    "contact", "location"
                ]):
                    decision = "general_info"
                
                # Default to general_info for ambiguous queries
                else:
                    decision = "general_info"

        if decision not in {"general_info", "timetable", "degree_advisor"}:
            decision = "general_info"

        updated_route = state.get("route", []) + [f"student_supervisor:routed_to:{decision}"]
        debug_msg = f"[STUDENT_SUP] Routing decision => {decision}"
        print(debug_msg)

        return Command(
            goto=decision,
            update={
                **state,
                "route": updated_route,
                "messages": state.get("messages", []) + [AIMessage(content=debug_msg, name="student_supervisor")],
            },
        )

    return node


def build_student_graph(general_info_node, timetable_node, degree_advisor_node):
    graph = StateGraph(StudentState)

    graph.add_node("student_router", create_student_supervisor_node())
    graph.add_node("general_info", general_info_node)
    graph.add_node("timetable", timetable_node)
    graph.add_node("degree_advisor", degree_advisor_node)

    graph.set_entry_point("student_router")
    graph.add_edge("general_info", END)
    graph.add_edge("timetable", END)
    graph.add_edge("degree_advisor", END)

    return graph.compile()
