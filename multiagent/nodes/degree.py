import sys
from pathlib import Path
from typing import Dict, Any, Literal

# Add the root directory to the Python path so we can import from root modules
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage

from ..agents.degree_advisor_agent import DegreeReactAgentBuilder, DegreeAdvisorAgent


class ConversationState(Dict[str, Any]):
    pass


def _route_degree(state: ConversationState) -> Literal["degree_info", "done"]:
    q = (state.get("question") or "").strip()
    if not q:
        return "done"
    return "degree_info"


def build_degree_graph():
    graph = StateGraph(ConversationState)

    try:
        builder = DegreeReactAgentBuilder()
        agent = builder.get_agent()
    except Exception:
        agent = None

    def router_node(state: ConversationState, config: RunnableConfig = None) -> ConversationState:
        return state

    def degree_info_node(state: ConversationState, config: RunnableConfig = None) -> ConversationState:
        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        try:
            if agent is not None:
                final_answer = ""
                config_dict = {"configurable": {"thread_id": f"degree_react_node::{session_id}"}}
                for step in agent.stream(
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
                # Fallback: simple RAG agent
                answer = _get_simple().invoke(question)
        except Exception:
            answer = f"I'm your degree advisor assistant. Question: {question}"
        if not isinstance(answer, str) or not answer.strip():
            answer = f"I'm your degree advisor assistant. Question: {question}"
        return {**state, "result": answer}

    graph.add_node("router", router_node)
    graph.add_node("degree_info", degree_info_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _route_degree, {
        "degree_info": "degree_info",
        "done": END,
    })
    graph.add_edge("degree_info", END)

    return graph.compile()


# Export compiled node
degree_router_node = build_degree_graph()


# Lazy fallback singleton
_SIMPLE = None


def _get_simple():
    global _SIMPLE
    if _SIMPLE is None:
        try:
            _SIMPLE = DegreeAdvisorAgent()
        except Exception:
            class _Fallback:
                def invoke(self, q: str) -> str:
                    q = q or ""
                    return f"I'm your degree advisor assistant. Question: {q}"
            _SIMPLE = _Fallback()
    return _SIMPLE


def run_degree(question: str, session_id: str = "default") -> str:
    state: ConversationState = {"question": question}
    route = _route_degree(state)
    if route == "degree_info":
        try:
            try:
                builder = DegreeReactAgentBuilder()
                agent = builder.get_agent()
            except Exception:
                agent = None
            if agent is not None:
                final_answer = ""
                config_dict = {"configurable": {"thread_id": f"degree_react_direct::{session_id}"}}
                for step in agent.stream(
                    {"messages": [HumanMessage(content=question)]},
                    config_dict,
                    stream_mode="values",
                ):
                    if step.get("messages"):
                        last_msg = step["messages"][-1]
                        if hasattr(last_msg, 'content') and isinstance(last_msg.content, str):
                            final_answer = last_msg.content
                ans = final_answer
            else:
                ans = _get_simple().invoke(question)
        except Exception:
            ans = ""
        if not isinstance(ans, str) or not ans.strip():
            ans = f"I'm your degree advisor assistant. Question: {question}"
        return ans
    return ""
