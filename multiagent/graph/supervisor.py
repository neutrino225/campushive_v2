import sys
from pathlib import Path
from typing import Dict, Any, Literal, TypedDict, List, AsyncGenerator

# Add the root directory to the Python path so we can import from root modules
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from ..nodes.student import student_router_node, run_student, run_student_streaming, run_general
from ..agents.faculty_agent import FacultyAgent
from ..agents.faculty_react_agent import FacultyReactAgentBuilder
from ..routing.classifiers import classify_supervisor
from ..memory import memory_manager, ConversationTurn
from config import llm


class SupervisorState(TypedDict):
    question: str
    result: str
    route: List[str]
    session_id: str
    conversation_history: List[ConversationTurn]


def _route_supervisor(state: SupervisorState) -> Literal["student", "faculty", "direct", "done"]:
    q = (state.get("question") or "").lower()
    if not q.strip():
        return "done"
    
    # Get conversation history for context-aware routing
    session_id = state.get("session_id", "default")
    history = state.get("conversation_history", [])
    
    # Enhance question with context if there's relevant history
    enhanced_question = q
    if history:
        # Look for context clues in recent conversation
        last_turn = history[-1] if history else None
        if last_turn:
            # If the last interaction was about a specific person, maintain that context
            if any(keyword in last_turn.agent_response.lower() for keyword in ["dr.", "prof", "professor", "head", "department"]):
                enhanced_question = f"Following up on previous question about faculty: {q}"
            elif any(keyword in last_turn.agent_response.lower() for keyword in ["degree", "program", "course", "admission"]):
                enhanced_question = f"Following up on previous question about academic programs: {q}"
    
    # Use LLM classifier with keyword fallback
    route = state.get("route", [])
    classification = classify_supervisor(enhanced_question, llm)
    state['route'] = route + [f"supervisor:route_to:{classification}"]
    return classification


def build_supervisor_graph():
    graph = StateGraph(SupervisorState)

    # Nodes
    async def router_node(state: SupervisorState, config: RunnableConfig = None) -> AsyncGenerator[SupervisorState, None]:
        # Initialize state with conversation history and routing
        session_id = state.get("session_id", "default")
        conversation_history = memory_manager.get_history(session_id)
        
        yield {
            **state, 
            "route": state.get("route", []),
            "conversation_history": conversation_history
        }

    async def student_node(state: SupervisorState, config: RunnableConfig = None) -> AsyncGenerator[SupervisorState, None]:
        q = state.get("question", "")
        session_id = state.get("session_id", "default")
        current_route = state.get("route", [])
        
        # Add conversation context to the question
        context = memory_manager.get_last_context(session_id, last_n=2)
        enhanced_question = f"{context}\n{q}" if context else q
        
        partial_result = ""
        try:
            for chunk in run_student_streaming(enhanced_question, session_id=session_id):
                partial_result += chunk
                yield {**state, "result": partial_result, "route": current_route + ["student_agent"]}
        except Exception as e:
            # Re-raise API errors immediately instead of falling back
            raise RuntimeError(f"Student agent API error: {e}") from e

    # Reuse agents for efficiency
    faculty_basic_agent = FacultyAgent(debug=False)
    try:
        faculty_react_builder = FacultyReactAgentBuilder()
        faculty_react_agent = faculty_react_builder.get_agent()
    except Exception:
        faculty_react_agent = None

    async def faculty_node_runner(state: SupervisorState, config: RunnableConfig = None) -> AsyncGenerator[SupervisorState, None]:
        q = state.get("question", "")
        session_id = state.get("session_id", "default")
        current_route = state.get("route", [])
        history = state.get("conversation_history", [])
        
        # Add conversation context to the question for faculty queries
        context = memory_manager.get_last_context(session_id, last_n=4)
        enhanced_question = f"{context}\n{q}" if context else q

        # Extract an explicit person hint from history ONLY for pronoun-based follow-ups
        # Avoid injecting when the latest question names explicit people or multiple entities.
        try:
            import re as _re
            latest = q or ""
            has_email_in_query = bool(_re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", latest))
            has_titled_name = bool(_re.search(r"\b(?:dr\.|prof(?:essor)?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", latest))
            mentions_multiple = bool(_re.search(r"\b(and|,|;|\band\b)\b", latest, flags=_re.IGNORECASE))
            has_pronoun = bool(_re.search(r"\b(his|her|their|him|them)\b", latest, flags=_re.IGNORECASE))

            if has_pronoun and not (has_email_in_query or has_titled_name or mentions_multiple):
                hint_email = None
                hint_name = None
                for turn in reversed(history or []):
                    if getattr(turn, "agent_response", None) and not hint_email:
                        m = _re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", turn.agent_response)
                        if m:
                            hint_email = m.group(0)
                    if getattr(turn, "agent_response", None) and not hint_name:
                        n = _re.search(r"\b(?:dr\.|prof(?:essor)?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", turn.agent_response)
                        if n:
                            hint_name = n.group(0)
                    if hint_email and hint_name:
                        break
                if hint_email:
                    enhanced_question = f"{enhanced_question}\nPerson: {hint_email}"
                elif hint_name:
                    enhanced_question = f"{enhanced_question}\nPerson: {hint_name}"
        except Exception:
            pass
        
        partial_result = ""
        try:
            if faculty_react_agent is not None:
                # Use tool-enabled agent with session-scoped memory
                config_dict = {"configurable": {"thread_id": f"faculty_react::{session_id}"}}
                final_answer = ""
                for step in faculty_react_agent.stream(
                    {"messages": [ {"type": "human", "content": enhanced_question} ]},
                    config_dict,
                    stream_mode="values",
                ):
                    if step.get("messages"):
                        last_msg = step["messages"][-1]
                        if hasattr(last_msg, "content") and isinstance(last_msg.content, str):
                            final_answer = last_msg.content
                partial_result = final_answer
                yield {**state, "result": partial_result, "route": current_route + ["faculty_react_agent"]}
            else:
                # Fallback to basic faculty agent
                for chunk in faculty_basic_agent.stream_answer(enhanced_question):
                    partial_result += chunk
                    yield {**state, "result": partial_result, "route": current_route + ["faculty_agent"]}
        except Exception as e:
            # Re-raise API errors immediately instead of masking with fallback messages
            raise RuntimeError(f"Faculty agent API error: {e}") from e
        # Fallback to general collection only if strict not-found token
        if partial_result.strip() == "NOT_FOUND_IN_DOCUMENTS":
            fallback_result = ""
            for chunk in run_general(enhanced_question):
                fallback_result += chunk
                yield {**state, "result": fallback_result, "route": current_route + ["faculty_agent", "fallback_to_general"]}
            if fallback_result.strip() == "NOT_FOUND_IN_DOCUMENTS":
                yield {**state, "result": "I'm sorry, I couldn't find information about that in our records.", "route": current_route + ["faculty_agent", "fallback_to_general"]}

    async def direct_node(state: SupervisorState, config: RunnableConfig = None) -> AsyncGenerator[SupervisorState, None]:
        q = state.get("question", "").lower()
        current_route = state.get("route", [])
        if any(g in q for g in ["hi", "hello", "hey", "salam", "assalam"]):
            result = "Hello! How can I help you today?"
            route = current_route + ["direct_greeting"]
        elif any(t in q for t in ["thanks", "thank you"]):
            result = "You're welcome!"
            route = current_route + ["direct_thanks"]
        elif any(phrase in q for phrase in [
            "what was the last question",
            "what did i ask last",
            "previous question",
            "last question i asked",
        ]):
            # Reflect last user message from memory
            session_id = state.get("session_id", "default")
            hist = memory_manager.get_history(session_id)
            last_q = ""
            for turn in reversed(hist or []):
                if getattr(turn, "user_message", None):
                    last_q = turn.user_message
                    break
            if last_q:
                result = f"Your last question was: {last_q}"
            else:
                result = "I don't have any previous question recorded in this session."
            route = current_route + ["direct_memory_query"]
        else:
            # Fallback response
            result = "How can I assist you with university-related queries?"
            route = current_route + ["direct_fallback"]
        yield {**state, "result": result, "route": route}

    graph.add_node("router", router_node)
    graph.add_node("student", student_node)
    graph.add_node("faculty", faculty_node_runner)
    graph.add_node("direct", direct_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _route_supervisor, {
        "student": "student",
        "faculty": "faculty",
        "direct": "direct",
        "done": END,
    })
    graph.add_edge("student", END)
    graph.add_edge("faculty", END)
    graph.add_edge("direct", END)

    return graph.compile()


supervisor_graph = build_supervisor_graph()


async def run_supervisor_async(question: str, session_id: str = "default") -> dict:
    """Async runner that streams the graph and returns the final 'result' string."""
    final_result = ""
    final_state = {}
    try:
        initial_state = {
            "question": question,
            "session_id": session_id,
            "route": [],
            "result": "",
            "conversation_history": []
        }
        
        async for event in supervisor_graph.astream_events(initial_state, version="v1"):
            kind = event["event"]
            if kind == "on_chain_end":
                node_name = event["name"]
                if node_name in ["student", "faculty", "direct"]:
                    data = event["data"].get("output")
                    if data and "result" in data:
                        final_result = data["result"]
                        final_state.update(data)
                        break
                        
    except Exception as e:
        return {"response": f"Error processing question: {str(e)}", "route": []}
    
    # Only provide fallback if no result was obtained at all
    if not final_result.strip():
        final_result = "I'm sorry, I couldn't process your question. Please try rephrasing it."

    # Normalize any multi-word explanatory output that contains the token
    # so callers receive exactly the single token when no docs were found.
    if "NOT_FOUND_IN_DOCUMENTS" in final_result:
        final_result = "NOT_FOUND_IN_DOCUMENTS"

    route = final_state.get("route", [])
    
    # Store conversation turn in memory
    memory_manager.add_turn(session_id, question, final_result, route)
    
    return {"response": final_result, "route": route}


def run_supervisor(question: str, session_id: str = "default") -> dict:
    """Synchronous wrapper for the async supervisor function."""
    import asyncio
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're in an async context, we can't use run()
            # This is a fallback for sync usage
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, run_supervisor_async(question, session_id))
                return future.result()
        else:
            return asyncio.run(run_supervisor_async(question, session_id))
    except Exception as e:
        return {"response": f"Error processing question: {str(e)}", "route": []}
