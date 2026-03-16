import sys
from pathlib import Path
from typing import List

root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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


def general_info_node():
    from ..nodes.student import _get_engine
    from ..memory import memory_manager

    async def node(state: StudentState):
        q = state.get("question", "")
        session_id = state.get("session_id", "default")
        route = state.get("route", [])
        eng = _get_engine()

        # Include conversation context for better responses
        context = memory_manager.get_last_context(session_id, last_n=3)
        enhanced_q = f"{context}\n{q}" if context else q

        # Stream tokens/chunks if available
        accumulated = ""
        try:
            for chunk in eng.stream_answer(enhanced_q):
                accumulated += chunk
                yield {**state, "result": accumulated, "route": route + ["general_info:streaming"]}
        except Exception as e:
            raise RuntimeError(f"General agent API error: {e}") from e

        yield {
            **state,
            "result": accumulated,
            "route": route + ["general_info:completed"],
            "messages": state.get("messages", []) + [AIMessage(content=accumulated, name="general_info")],
        }

    return node


def timetable_node():
    from ..nodes.student import _answer_timetable_query
    from ..memory import memory_manager

    async def node(state: StudentState):
        q = state.get("question", "")
        session_id = state.get("session_id", "default")
        route = state.get("route", [])
        
        # Use prior user timetable queries as optional context for follow-ups
        # like "Monday only", but avoid mixing assistant text into the matcher.
        history = memory_manager.get_history(session_id) or []
        recent_turns = history[-3:]
        recent_user_queries = [turn.user_message for turn in recent_turns if getattr(turn, "user_message", None)]
        
        accumulated = ""
        try:
            accumulated = _answer_timetable_query(q, conversation_history=recent_user_queries)
            yield {**state, "result": accumulated, "route": route + ["timetable:streaming"]}
        except Exception as e:
            raise RuntimeError(f"Timetable agent API error: {e}") from e

        yield {
            **state,
            "result": accumulated,
            "route": route + ["timetable:completed"],
            "messages": state.get("messages", []) + [AIMessage(content=accumulated, name="timetable")],
        }

    return node


def degree_advisor_node():
    from ..agents.degree_advisor_agent import DegreeReactAgentBuilder
    from ..nodes.student import _get_deg_simple
    from ..memory import memory_manager

    async def node(state: StudentState):
        q = state.get("question", "")
        session_id = state.get("session_id", "default")
        route = state.get("route", [])

        # Prefer ReAct streaming agent
        try:
            builder = DegreeReactAgentBuilder()
            agent = builder.get_agent()
        except Exception:
            agent = None

        accumulated = ""
        try:
            if agent is not None:
                config_dict = {"configurable": {"thread_id": f"student_degree::{session_id}"}}
                sys_text = getattr(builder, "system_prompt_text", "")
                
                # Build messages with conversation context
                msgs = []
                if sys_text:
                    msgs.append(SystemMessage(content=sys_text))
                
                # Include recent conversation history for context-aware responses
                history = memory_manager.get_history(session_id) or []
                recent_turns = history[-3:]  # Last 3 turns for context
                
                # Add conversation history as messages
                for turn in recent_turns:
                    msgs.append(HumanMessage(content=turn.user_message))
                    msgs.append(AIMessage(content=turn.agent_response))
                
                # Add current question
                msgs.append(HumanMessage(content=q))
                
                # Stream agent responses
                for step in agent.stream({"messages": msgs}, config_dict, stream_mode="values"):
                    if step.get("messages"):
                        last_msg = step["messages"][-1]
                        if hasattr(last_msg, "content") and isinstance(last_msg.content, str):
                            accumulated = last_msg.content
                            yield {**state, "result": accumulated, "route": route + ["degree_advisor:streaming"]}
            else:
                # fallback simple degree advisor with context
                context = memory_manager.get_last_context(session_id, last_n=3)
                enhanced_q = f"{context}\n{q}" if context else q
                ans = _get_deg_simple().invoke(enhanced_q)
                accumulated = ans
                yield {**state, "result": accumulated, "route": route + ["degree_advisor:streaming"]}
        except Exception as e:
            raise RuntimeError(f"Degree advisor API error: {e}") from e

        yield {
            **state,
            "result": accumulated,
            "route": route + ["degree_advisor:completed"],
            "messages": state.get("messages", []) + [AIMessage(content=accumulated, name="degree_advisor")],
        }

    return node
