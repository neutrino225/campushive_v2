import sys
from pathlib import Path
from typing import Dict, Any, Literal
import logging

# Add the root directory to the Python path so we can import from root modules
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from langchain.prompts import PromptTemplate
from langchain_core.messages import HumanMessage

from ..prompts.faculty_router import faculty_router_prompt
from ..agents.faculty_react_agent import FacultyAgent, FacultyReactAgentBuilder
from ..agents.obe_agent.obe_agent import OBEAgent
from config import llm
from ..routing.classifiers import classify_faculty

# Setup logger
logger = logging.getLogger(__name__)


class ConversationState(Dict[str, Any]):
    pass


def _extract_outcomes(text: str, outcome_type: str) -> list[str]:
    """Extract CLOs or PLOs from the text.
    
    Args:
        text: The text to extract from
        outcome_type: Either "clo" or "plo"
    
    Returns:
        List of extracted outcomes
    """
    import re
    
    outcomes = []
    outcome_type_upper = outcome_type.upper()
    
    # Pattern 1: "CLO 1: description" or "- CLO 1: description"
    pattern1 = rf"[-•*]?\s*{outcome_type_upper}\s*(\d+)\s*:?\s*(.+?)(?=\n|$)"
    matches1 = re.finditer(pattern1, text, re.IGNORECASE | re.MULTILINE)
    for match in matches1:
        outcomes.append(match.group(2).strip())
    
    # Pattern 2: Numbered list after "CLOs:" or "PLOs:" header
    section_pattern = rf"{outcome_type_upper}s?\s*:?\s*\n((?:[-•*]?\s*.+\n?)+)"
    section_match = re.search(section_pattern, text, re.IGNORECASE | re.MULTILINE)
    if section_match:
        section_text = section_match.group(1)
        # Extract each line that starts with a bullet or dash
        line_pattern = r"[-•*]?\s*(.+?)(?=\n|$)"
        for line_match in re.finditer(line_pattern, section_text, re.MULTILINE):
            outcome = line_match.group(1).strip()
            if outcome and not outcome.lower().startswith(('clo', 'plo', 'map', 'these')):
                # Remove leading "CLO X:" or "PLO X:" if present
                outcome = re.sub(rf"^{outcome_type_upper}\s*\d+\s*:?\s*", "", outcome, flags=re.IGNORECASE)
                if outcome and outcome not in outcomes:
                    outcomes.append(outcome)
    
    return outcomes


def _route_faculty(state: ConversationState) -> Literal["faculty_info", "obe_mapping", "done"]:
    """Route faculty questions to either faculty_info or obe_mapping based on keywords."""
    q = (state.get("question") or "").lower()
    if not q.strip():
        return "done"
    
    # Check for OBE-related keywords
    obe_keywords = ["clo", "plo", "course learning outcome", "program learning outcome", 
                    "mapping", "map", "outcome", "align", "alignment"]
    if any(keyword in q for keyword in obe_keywords):
        return "obe_mapping"
    
    # Default to faculty info for all other faculty questions
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

    # Initialize OBE agent instance
    try:
        obe_agent = OBEAgent()
    except Exception:
        obe_agent = None

    # Nodes
    def router_node(state: ConversationState, config: RunnableConfig = None) -> ConversationState:
        # No-op; used only for conditional routing based on question
        return state

    def obe_mapping_node(state: ConversationState, config: RunnableConfig = None) -> ConversationState:
        """Handle CLO-PLO mapping requests."""
        question = state.get("question", "")
        session_id = state.get("session_id")
        user_id = state.get("user_id")
        
        try:
            if obe_agent is None:
                return {**state, "result": "OBE mapping service is currently unavailable. Please try again later."}
            
            # Try to extract CLOs and PLOs from the question
            clos = _extract_outcomes(question, "clo")
            plos = _extract_outcomes(question, "plo")
            
            logger.info(f"[FACULTY DEBUG] Extracted from question: clos={clos}, plos={plos}")
            logger.info(f"[FACULTY DEBUG] user_id={user_id}, session_id={session_id}")
            logger.info(f"[FACULTY DEBUG] Condition check: not clos={not clos}, not plos={not plos}, has user_id={bool(user_id)}, has session_id={bool(session_id)}")
            
            # If we don't have CLOs/PLOs from the question, try to extract from uploaded documents
            if (not clos or not plos) and user_id and session_id:
                logger.info(f"[FACULTY DEBUG] Calling extract_outcomes_from_document...")
                extraction_result = obe_agent.extract_outcomes_from_document(
                    user_id=user_id, 
                    session_id=str(session_id)
                )
                logger.info(f"[FACULTY DEBUG] Extraction result: {extraction_result}")
                
                if "error" not in extraction_result:
                    if not clos and extraction_result.get("clos"):
                        clos = extraction_result["clos"]
                    if not plos and extraction_result.get("plos"):
                        plos = extraction_result["plos"]
            
            # If we have both CLOs and PLOs, generate the mapping
            if clos and plos:
                result = obe_agent.run(
                    clos=clos, 
                    plos=plos, 
                    user_id=user_id, 
                    session_id=str(session_id) if session_id else None
                )
                return {**state, "result": result}
            
            # If still no outcomes, provide instructions
            if user_id and session_id:
                instructions = (
                    "I can help you map Course Learning Outcomes (CLOs) to Program Learning Outcomes (PLOs).\n\n"
                    "I tried to extract CLOs and PLOs from your uploaded document, but couldn't find them. "
                    "Please either:\n"
                    "1. Upload a course outline/syllabus document that contains CLOs and PLOs, or\n"
                    "2. Provide them directly in your message\n\n"
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
            else:
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
            
            return {**state, "result": instructions}
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            return {**state, "result": f"Error processing OBE mapping request: {str(e)}\n\nDetails: {error_details}"}

    def faculty_info_node(state: ConversationState, config: RunnableConfig = None) -> ConversationState:
        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        try:
            # Prefer the tool-enabled agent when available for better observability and tools
            if react_agent is not None:
                final_answer = ""
                config_dict = {"configurable": {"thread_id": f"faculty_react_node::{session_id}"}}
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
    graph.add_node("obe_mapping", obe_mapping_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _route_faculty, {
        "faculty_info": "faculty_info",
        "obe_mapping": "obe_mapping",
        "done": END,
    })
    graph.add_edge("faculty_info", END)
    graph.add_edge("obe_mapping", END)

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
