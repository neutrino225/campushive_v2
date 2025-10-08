import sys
from pathlib import Path
from typing import Dict, Any, Literal

# Add the root directory to the Python path so we can import from root modules
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from langchain.prompts import PromptTemplate
from langchain_core.messages import HumanMessage

from ..prompts.faculty_router import faculty_router_prompt
from ..agents.faculty_agent import FacultyAgent
from ..agents.faculty_react_agent import FacultyReactAgentBuilder
from config import llm
from ..routing.classifiers import classify_faculty


class ConversationState(Dict[str, Any]):
    pass


def _route_faculty(state: ConversationState) -> Literal["faculty_info", "done"]:
    q = (state.get("question") or "").lower()
    if not q.strip():
        return "done"
    # All faculty questions go to faculty_info since we removed placeholder
    return "faculty_info"


def build_faculty_graph():
    graph = StateGraph(ConversationState)

    # Initialize faculty agent instance
    try:
        agent = FacultyAgent(debug=False)
    except Exception:
        agent = None

    # Optional: tool-enabled ReAct agent for richer graphs/tool calls
    try:
        react_builder = FacultyReactAgentBuilder()
        react_agent = react_builder.get_agent()
    except Exception:
        react_agent = None

    # Nodes
    def router_node(state: ConversationState, config: RunnableConfig = None) -> ConversationState:
        # No-op; used only for conditional routing based on question
        return state

    def faculty_info_node(state: ConversationState, config: RunnableConfig = None) -> ConversationState:
        question = state.get("question", "")
        try:
            # Prefer the tool-enabled agent when available for better observability and tools
            if react_agent is not None:
                final_answer = ""
                config_dict = {"configurable": {"thread_id": "faculty_react_node"}}
                for step in react_agent.stream(
                    {"messages": [HumanMessage(content=question)]},
                    config_dict,
                    stream_mode="values",
                ):
                    if step.get("messages"):
                        last_msg = step["messages"][-1]
                        if hasattr(last_msg, "content") and isinstance(last_msg.content, str):
                            final_answer = last_msg.content
                answer = final_answer
            else:
                faculty_agent = agent or _get_faculty_agent()
                answer = faculty_agent.answer(question, stream=False)
        except Exception:
            answer = f"I'm your faculty information assistant. Question: {question}"
        if not isinstance(answer, str) or not answer.strip():
            answer = f"I'm your faculty information assistant. Question: {question}"
        return {**state, "result": answer}

    graph.add_node("router", router_node)
    graph.add_node("faculty_info", faculty_info_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _route_faculty, {
        "faculty_info": "faculty_info",
        "done": END,
    })
    graph.add_edge("faculty_info", END)

    return graph.compile()


# Export compiled node
faculty_router_node = build_faculty_graph()


# Lazy singleton for direct routing helper
_FACULTY_AGENT = None


def _get_faculty_agent():
    global _FACULTY_AGENT
    if _FACULTY_AGENT is None:
        try:
            _FACULTY_AGENT = FacultyAgent(debug=False)
        except Exception:
            class _FallbackFacultyAgent:
                def answer(self, q: str, stream: bool = False) -> str:
                    q = q or ""
                    return f"I'm your faculty information assistant. Question: {q}"
            _FACULTY_AGENT = _FallbackFacultyAgent()
    return _FACULTY_AGENT


def run_faculty(question: str) -> str:
    """Direct runner (non-graph) for faculty routing to ensure deterministic test behavior."""
    state: ConversationState = {"question": question}
    route = _route_faculty(state)
    if route == "faculty_info":
        try:
            ans = _get_faculty_agent().answer(question, stream=False)
        except Exception:
            ans = ""
        if not isinstance(ans, str) or not ans.strip():
            ans = f"I'm your faculty information assistant. Question: {question}"
        return ans
    return ""


def run_faculty_streaming(question: str):
    """Direct runner with streaming enabled for faculty routing. Yields chunks."""
    state: ConversationState = {"question": question}
    route = _route_faculty(state)
    if route == "faculty_info":
        try:
            for chunk in _get_faculty_agent().stream_answer(question):
                yield chunk
        except Exception:
            yield f"I'm your faculty information assistant. Question: {question}"
    else:
        yield ""
