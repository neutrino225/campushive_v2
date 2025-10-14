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


class FacultyState(TypedDict):
    question: str
    result: str
    route: List[str]
    session_id: str
    conversation_history: List
    user_role: str
    messages: List


def create_faculty_supervisor_node():
    """Route inside faculty domain: faculty_info or obe."""
    system_prompt = (
        "You are the FACULTY domain supervisor. Decide which subagent should handle the question.\n"
        "You have access to the recent conversation history. Use it to understand context and references.\n"
        "Return EXACTLY one of: faculty_info, obe\n\n"
        "Examples:\n"
        "Q: 'Who teaches DB systems?'\nA: faculty_info\n"
        "Q: 'Map CLO1 to PLO3'\nA: obe\n"
    )

    async def node(state: FacultyState):
        from multiagent.memory import memory_manager
        
        q = state.get("question", "")
        session_id = state.get("session_id", "default")
        
        # Include conversation context for intelligent routing
        context = memory_manager.get_last_context(session_id, last_n=5)
        question_with_context = f"{context}\n{q}" if context else q
        
        msgs = [SystemMessage(content=system_prompt), HumanMessage(content=f"Question: {question_with_context}")]
        try:
            resp = await llm.ainvoke(msgs)
            decision = (resp.content or "").strip().lower()
        except Exception:
            decision = "obe" if any(k in q.lower() for k in ["clo", "plo"]) else "faculty_info"

        if decision not in {"faculty_info", "obe"}:
            decision = "faculty_info"

        updated_route = state.get("route", []) + [f"faculty_supervisor:routed_to:{decision}"]
        debug_msg = f"[FACULTY_SUP] Routing decision => {decision}"
        print(debug_msg)

        return Command(
            goto=decision,
            update={
                **state,
                "route": updated_route,
                "messages": state.get("messages", []) + [AIMessage(content=debug_msg, name="faculty_supervisor")],
            },
        )

    return node


def build_faculty_graph(faculty_info_node, obe_node):
    graph = StateGraph(FacultyState)

    graph.add_node("faculty_router", create_faculty_supervisor_node())
    graph.add_node("faculty_info", faculty_info_node)
    graph.add_node("obe", obe_node)

    graph.set_entry_point("faculty_router")
    graph.add_edge("faculty_info", END)
    graph.add_edge("obe", END)

    return graph.compile()
