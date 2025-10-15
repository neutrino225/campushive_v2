import sys
import json
import re
import hashlib
from pathlib import Path
from typing import Dict, Any, Literal, TypedDict, List, AsyncGenerator, Optional

# Add the root directory to the Python path so we can import from root modules
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from ..nodes.student import student_router_node, run_student, run_student_streaming, run_general
from ..agents.faculty_react_agent import FacultyAgent, FacultyReactAgentBuilder
from ..agents.exam_react_agent import ExamReactAgent  # New simplified agent
from ..agents.obe_agent.obe_agent import OBEAgent
from ..routing import classifiers as routing_classifiers
from ..memory import memory_manager, ConversationTurn
from config import llm, small_llm


class SupervisorState(TypedDict):
    question: str
    result: str
    route: List[str]
    session_id: str
    conversation_history: List[ConversationTurn]
    user_role: str


# ---------------- LLM micro-resolver for person disambiguation ----------------
_person_resolver_cache: Dict[str, Dict[str, str]] = {}


def _make_cache_key(session_id: str, latest_q: str, history: List[ConversationTurn], last_n: int = 3) -> str:
    segs: List[str] = [session_id or "default", latest_q or ""]
    recent = history[-last_n:] if history and len(history) > last_n else (history or [])
    for t in recent:
        u = getattr(t, "user_message", "") or ""
        a = getattr(t, "agent_response", "") or ""
        segs.append(f"U:{u}\nA:{a}")
    raw = "\n---\n".join(segs)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_json_loose(text: str) -> Dict[str, Any]:
    """Extract first JSON object from text; tolerate code fences and extra text."""
    if not text:
        return {}
    # Strip fences if present
    text = text.strip()
    text = re.sub(r"^```(json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # Fallback: find first {...} block
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


def _validate_email(s: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", s or ""))


_SMALL_TALK_MATCHERS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(hi|hello|hey|howdy|salam|assalam(?:ualaikum)?)\b",
        r"\b(good\s+(morning|afternoon|evening|day))\b",
        r"\b(bye|goodbye|see you|later)\b",
        r"\b(thanks|thank\s+you|appreciate\s+it)\b",
        r"\b(great|awesome|cool|nice)\b\s*(thanks|thank\s+you)?$",
    ]
]

_FOLLOW_UP_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bwhat about\b",
        r"\bhow about\b",
        r"\bwhat else\b",
        r"\banything else\b",
        r"\btell me more\b",
        r"\bcan you (?:explain|elaborate)\b",
        r"\bmore detail\b",
        r"\bgive me another\b",
        r"\bany other\b",
        r"\bagain\b",
    ]
]

_FOLLOW_UP_PRONOUNS = re.compile(r"\b(it|that|this|those|them|they|their|his|her|him)\b", re.IGNORECASE)


def _is_small_talk_message(question: str) -> bool:
    text = (question or "").strip()
    if not text:
        return False
    for matcher in _SMALL_TALK_MATCHERS:
        if matcher.search(text):
            return True
    # Very short acknowledgements like "ok" or "sure"
    lowered = text.lower()
    if lowered in {"ok", "okay", "sure", "alright", "sounds good"}:
        return True
    return False


def _generate_small_talk_reply(question: str) -> str:
    lowered = (question or "").strip().lower()
    if not lowered:
        return "Hi there! How can I help you with CampusHive today?"
    if re.search(r"\b(hi|hello|hey|howdy|salam|assalam(?:ualaikum)?)\b", lowered):
        return "Hello! I'm here to help with university questions whenever you're ready."
    if re.search(r"\bgood\s+(morning|afternoon|evening|day)\b", lowered):
        return "Good day! Let me know how I can assist you with campus information."
    if re.search(r"\b(thanks?|thank\s+you|appreciate(?:\s+it)?)\b", lowered):
        return "You're welcome! Feel free to ask if you need anything else."
    if re.search(r"\b(bye|goodbye|see you|later)\b", lowered):
        return "Goodbye! Reach out anytime you have more questions."
    if lowered in {"ok", "okay", "sure", "alright", "sounds good"}:
        return "Got it. Let me know if there's anything else you need."
    return "Happy to help! What would you like to know about next?"


def _infer_last_primary_route(history: List[ConversationTurn]) -> Optional[Literal["student", "faculty", "exam"]]:
    for turn in reversed(history or []):
        for step in reversed(turn.route or []):
            if step.endswith("student_agent"):
                return "student"
            if step.endswith("faculty_agent") or step.endswith("faculty_react_agent"):
                return "faculty"
            if step.endswith("exam_agent") or step.endswith("exam_react_agent"):
                return "exam"
    return None


def _is_follow_up_question(question: str, history: List[ConversationTurn]) -> bool:
    text = (question or "").strip()
    if not text or not history:
        return False
    lowered = text.lower()
    # Pattern-based detection
    for pattern in _FOLLOW_UP_PATTERNS:
        if pattern.search(lowered):
            return True
    words = lowered.split()
    if len(words) <= 2 and lowered in {"why", "how", "what", "and?"}:
        return True
    if len(words) <= 8 and _FOLLOW_UP_PRONOUNS.search(lowered):
        return True
    if lowered.startswith("and ") or lowered.startswith("also "):
        return True
    return False


def _heuristic_primary_route(question: str) -> Literal["student", "faculty", "exam"]:
    lowered = (question or "").lower()
    if any(keyword in lowered for keyword in ["exam", "quiz", "test", "paper", "assessment", "practice"]):
        return "exam"
    if any(keyword in lowered for keyword in ["professor", "prof", "dr.", "faculty", "lecturer", "instructor", "advisor", "hod", "head of"]):
        return "faculty"
    return "student"


def _llm_person_resolver(latest_q: str, history: List[ConversationTurn], session_id: str, last_n: int = 3) -> Dict[str, str]:
    """Use LLM to resolve the likely person being referred to (by name/email).

    Returns a dict subset of {"person_name": str, "email": str}. Empty dict if not found.
    Raises on API errors per project conventions.
    """
    cache_key = _make_cache_key(session_id, latest_q, history, last_n=last_n)
    if cache_key in _person_resolver_cache:
        return _person_resolver_cache[cache_key]

    # Build compact history context (last n turns)
    recent = history[-last_n:] if history and len(history) > last_n else (history or [])
    ctx_lines: List[str] = []
    for t in recent:
        if getattr(t, "user_message", None):
            ctx_lines.append(f"User: {t.user_message}")
        if getattr(t, "agent_response", None):
            # Truncate to keep prompt small
            resp = (t.agent_response or "")[:500]
            ctx_lines.append(f"Assistant: {resp}")
    ctx = "\n".join(ctx_lines)

    system_inst = (
        "You are a strict JSON micro-classifier that identifies the specific faculty person referenced in the user's latest message,"
        " using only the brief conversation context."
        " Output ONLY a single JSON object with up to two fields: person_name and email."
        " If uncertain, output {}. Never invent emails or names."
    )

    schema_hint = (
        "Schema: {\"person_name\": string, \"email\": string}. Include a field only if confidently known."
    )

    user_prompt = (
        f"Context (last {last_n} turns):\n{ctx}\n\n"
        f"Latest message: {latest_q}\n\n"
        f"{schema_hint}"
    )

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        resp = small_llm.invoke([SystemMessage(content=system_inst), HumanMessage(content=user_prompt)])
        content = getattr(resp, "content", "")
        data = _parse_json_loose(content)
        out: Dict[str, str] = {}
        if isinstance(data, dict):
            name = data.get("person_name")
            email = data.get("email")
            if isinstance(name, str) and name.strip():
                out["person_name"] = name.strip()
            if isinstance(email, str) and _validate_email(email.strip()):
                out["email"] = email.strip()
        _person_resolver_cache[cache_key] = out
        return out
    except Exception as e:
        # Re-raise per conventions (no silent fallback on API errors)
        raise RuntimeError(f"LLM person resolver error: {e}") from e


def _route_supervisor(state: SupervisorState) -> Literal["student", "faculty", "direct", "exam", "done"]:
    q = state.get("question", "")
    if not q.strip():
        return "done"
    
    # Get conversation history for context-aware routing
    session_id = state.get("session_id", "default")
    history = state.get("conversation_history", [])
    route = state.get("route", [])

    if _is_small_talk_message(q):
        classification: Literal["student", "faculty", "direct", "exam"] = "direct"
    else:
        prior_route = _infer_last_primary_route(history)
        if prior_route and _is_follow_up_question(q, history):
            classification = prior_route
        else:
            conversation_context = ""
            if history:
                recent_history = history[-3:] if len(history) > 3 else history
                context_parts = []
                for turn in recent_history:
                    if hasattr(turn, 'user_message') and hasattr(turn, 'agent_response'):
                        context_parts.append(f"User: {turn.user_message}")
                        context_parts.append(f"Assistant: {turn.agent_response[:200]}...")
                conversation_context = "\n".join(context_parts)
            classification = routing_classifiers.classify_supervisor(q, llm, conversation_context=conversation_context)
            if classification == "direct":
                classification = prior_route or _heuristic_primary_route(q)

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
        context = memory_manager.get_last_context(session_id, last_n=20)
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
    # Initialize OBE agent
    try:
        obe_agent = OBEAgent()
    except Exception:
        obe_agent = None
    # Simple exam agent will be instantiated lazily in the exam node
    exam_agent = None

    async def faculty_node_runner(state: SupervisorState, config: RunnableConfig = None) -> AsyncGenerator[SupervisorState, None]:
        q = state.get("question", "")
        session_id = state.get("session_id", "default")
        current_route = state.get("route", [])
        history = state.get("conversation_history", [])
        
        # Check if this is an OBE mapping request
        q_lower = q.lower()
        obe_keywords = ["clo", "plo", "course learning outcome", "program learning outcome", 
                        "mapping", "map", "outcome", "align", "alignment"]
        is_obe_request = any(keyword in q_lower for keyword in obe_keywords)
        
        # If it's an OBE request, use the OBE agent
        if is_obe_request and obe_agent is not None:
            try:
                # Extract CLOs and PLOs from the question
                from ..nodes.faculty import _extract_outcomes
                clos = _extract_outcomes(q, "clo")
                plos = _extract_outcomes(q, "plo")
                
                # If we have both CLOs and PLOs, generate the mapping
                if clos and plos:
                    result = obe_agent.run(clos=clos, plos=plos)
                    yield {**state, "result": result, "route": current_route + ["obe_agent"]}
                    return
                else:
                    # Provide instructions if CLOs/PLOs are not provided
                    instructions = (
                        "I can help you map Course Learning Outcomes (CLOs) to Program Learning Outcomes (PLOs).\n\n"
                        "To use this feature, please provide:\n"
                        "1. A list of CLOs (Course Learning Outcomes)\n"
                        "2. A list of PLOs (Program Learning Outcomes)\n\n"
                        "I will then generate a mapping table showing which CLOs align with which PLOs, "
                        "along with justifications for each mapping.\n\n"
                        "Example format:\n"
                        "```\n"
                        "Map these outcomes:\n\n"
                        "CLOs:\n"
                        "- CLO 1: Understand basic algorithms\n"
                        "- CLO 2: Implement data structures\n\n"
                        "PLOs:\n"
                        "- PLO 1: Apply knowledge of computing fundamentals\n"
                        "- PLO 2: Design and develop solutions\n"
                        "```"
                    )
                    yield {**state, "result": instructions, "route": current_route + ["obe_agent"]}
                    return
            except Exception as e:
                error_msg = f"Error processing OBE mapping request: {str(e)}"
                yield {**state, "result": error_msg, "route": current_route + ["obe_agent_error"]}
                return
        
        # Add conversation context to the question for faculty queries
        context = memory_manager.get_last_context(session_id, last_n=20)
        enhanced_question = f"{context}\n{q}" if context else q

        # Resolve person hint using LLM micro-resolver on pronoun-like follow-ups; fall back to regex scrape
        try:
            latest = q or ""
            has_email_in_query = bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", latest))
            has_titled_name = bool(re.search(r"\b(?:dr\.|prof(?:essor)?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", latest))
            mentions_multiple = bool(re.search(r"[,;]|\band\b", latest, flags=re.IGNORECASE))
            has_pronoun = bool(re.search(r"\b(his|her|their|him|them)\b", latest, flags=re.IGNORECASE))

            if has_pronoun and not (has_email_in_query or has_titled_name or mentions_multiple):
                # Primary: LLM micro-resolver (with caching and strict JSON)
                resolved = _llm_person_resolver(latest, history or [], session_id=session_id, last_n=3)
                if resolved.get("email"):
                    enhanced_question = f"{enhanced_question}\nPerson: {resolved['email']}"
                elif resolved.get("person_name"):
                    enhanced_question = f"{enhanced_question}\nPerson: {resolved['person_name']}"
                else:
                    # Fallback: scrape previous messages for a hint
                    hint_email = None
                    hint_name = None
                    for turn in reversed(history or []):
                        if getattr(turn, "agent_response", None) and not hint_email:
                            m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", turn.agent_response)
                            if m:
                                hint_email = m.group(0)
                        if getattr(turn, "agent_response", None) and not hint_name:
                            n = re.search(r"\b(?:dr\.|prof(?:essor)?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", turn.agent_response)
                            if n:
                                hint_name = n.group(0)
                        if hint_email and hint_name:
                            break
                    if hint_email:
                        enhanced_question = f"{enhanced_question}\nPerson: {hint_email}"
                    elif hint_name:
                        enhanced_question = f"{enhanced_question}\nPerson: {hint_name}"
        except Exception:
            # Do not block the route on resolver issues; the agent may still resolve
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
            # Re-raise API errors immediately - let the agent handle its own fallbacks
            raise RuntimeError(f"Faculty agent API error: {e}") from e
        # Fallback to general collection only if strict not-found token
        if partial_result.strip() == "NOT_FOUND_IN_DOCUMENTS":
            fallback_result = ""
            for chunk in run_general(enhanced_question):
                fallback_result += chunk
                yield {**state, "result": fallback_result, "route": current_route + ["faculty_agent", "fallback_to_general"]}
            if fallback_result.strip() == "NOT_FOUND_IN_DOCUMENTS":
                yield {**state, "result": "I'm sorry, I couldn't find information about that in our records.", "route": current_route + ["faculty_agent", "fallback_to_general"]}

    async def exam_node_runner(state: SupervisorState, config: RunnableConfig = None) -> AsyncGenerator[SupervisorState, None]:
        """
        ReAct-based exam generation node with built-in memory.
        The agent naturally handles conversation context, clarifications, and modifications.
        """
        question = state.get("question", "")
        current_route = state.get("route", [])
        user_role = state.get("user_role", "student")
        session_id = state.get("session_id", "default")
        user_id = state.get("user_id", None)  # Get user_id from state

        # Instantiate exam agent lazily
        nonlocal exam_agent
        if exam_agent is None:
            try:
                exam_agent = ExamReactAgent()
            except Exception as e:
                error_result = "Exam generation is currently unavailable."
                yield {**state, "result": error_result, "route": current_route + ["exam_agent_error"]}
                return
        
        try:
            # Stream the exam generation with full conversational context
            # The ReAct agent handles memory automatically through its checkpointer
            partial_result = ""
            async for chunk in exam_agent.stream_async(
                question, 
                session_id=session_id, 
                user_id=user_id,  # Pass user_id for uploaded document access
                user_role=user_role
            ):
                partial_result += chunk
                # Yield intermediate states for streaming
                yield {**state, "result": partial_result, "route": current_route + ["exam_react_agent"]}
            
            # Final yield with complete response
            yield {**state, "result": partial_result, "route": current_route + ["exam_react_agent"]}
            return
        except Exception as e:
            # Surface error via exam route
            error_result = f"Exam generation error: {e}"
            yield {**state, "result": error_result, "route": current_route + ["exam_agent_error"]}
            return


    async def direct_node(state: SupervisorState, config: RunnableConfig = None) -> AsyncGenerator[SupervisorState, None]:
        """Handle small talk, greetings, and acknowledgements without invoking the main LLM."""
        question = state.get("question", "")
        current_route = state.get("route", [])

        # Generate a lightweight acknowledgement for small-talk style messages
        response = _generate_small_talk_reply(question)
        yield {**state, "result": response, "route": current_route + ["small_talk"]}

    graph.add_node("router", router_node)
    graph.add_node("student", student_node)
    graph.add_node("faculty", faculty_node_runner)
    graph.add_node("direct", direct_node)
    graph.add_node("exam", exam_node_runner)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _route_supervisor, {
        "student": "student",
        "faculty": "faculty",
        "direct": "direct",
        "exam": "exam",
        "done": END,
    })
    graph.add_edge("student", END)
    graph.add_edge("faculty", END)
    graph.add_edge("direct", END)
    graph.add_edge("exam", END)

    return graph.compile()


supervisor_graph = build_supervisor_graph()


async def run_supervisor_async(question: str, session_id: str = "default", user_role: str = "student") -> dict:
    """Async runner that streams the graph and returns the final 'result' string."""
    final_result = ""
    final_state = {}
    try:
        initial_state = {
            "question": question,
            "session_id": session_id,
            "user_role": user_role,
            "route": [],
            "result": "",
            "conversation_history": []
        }
        
        async for event in supervisor_graph.astream_events(initial_state, version="v1"):
            kind = event["event"]
            if kind == "on_chain_end":
                node_name = event["name"]
                if node_name in ["student", "faculty", "direct", "exam"]:
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


def run_supervisor(question: str, session_id: str = "default", user_role: str = "student") -> dict:
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
                future = executor.submit(asyncio.run, run_supervisor_async(question, session_id, user_role))
                return future.result()
        else:
            return asyncio.run(run_supervisor_async(question, session_id, user_role))
    except Exception as e:
        return {"response": f"Error processing question: {str(e)}", "route": []}
