import sys
from pathlib import Path
from typing import Dict, Any, Literal, List, Annotated

# Use typing_extensions for Python < 3.12 compatibility
try:
    from typing_extensions import TypedDict
except ImportError:
    from typing import TypedDict

# Add the root directory to the Python path
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.types import Command
from langgraph.prebuilt import create_react_agent, InjectedState
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from ..agents.faculty_react_agent import FacultyReactAgentBuilder
from ..agents.exam_react_agent import ExamReactAgent
from ..agents.obe_agent.obe_agent import OBEAgent
from ..memory import memory_manager, ConversationTurn
from config import llm

# New hierarchical supervisors
from .main_supervisor import build_main_graph as build_main_supervisor_graph
from .student_supervisor import build_student_graph
from .faculty_supervisor import build_faculty_graph


# ============================================================================
# State Definition
# ============================================================================

class SupervisorState(TypedDict):
    """State for the supervisor graph with delegation."""
    question: str
    result: str
    route: List[str]
    session_id: str
    conversation_history: List[ConversationTurn]
    user_role: str
    messages: List  # For LangGraph message passing


# ============================================================================
# Handoff Tools - Core Delegation Mechanism
# ============================================================================

def create_handoff_tool(*, agent_name: str, description: str | None = None):
    """
    Create a handoff tool that the supervisor can use to delegate to a worker agent.
    
    Based on LangGraph's multi-agent supervisor pattern. When the supervisor calls
    this tool, it hands off control to the specified agent with the full state.
    
    Args:
        agent_name: Name of the agent to transfer to
        description: Description of what this agent does (shown to supervisor LLM)
    
    Returns:
        A tool function that returns a Command to transfer control
    """
    name = f"transfer_to_{agent_name}"
    description = description or f"Transfer task to {agent_name} agent."
    
    # Create a simple tool that doesn't require parameters
    # The tool will access state through InjectedState at runtime
    @tool(name, description=description)
    def handoff_tool() -> str:
        """Execute the handoff to the target agent."""
        # This tool just returns a confirmation string
        # The actual routing happens in the graph via Command
        return f"Transferring to {agent_name} agent..."
    
    # Store metadata for Command generation
    handoff_tool._agent_name = agent_name
    
    return handoff_tool


def create_task_delegation_handoff_tool(*, agent_name: str, description: str | None = None):
    """
    Create a handoff tool with explicit task description delegation.
    
    This version lets the supervisor formulate an explicit task for the worker,
    rather than passing the full conversation history. Useful for complex queries
    that need to be broken down.
    
    Args:
        agent_name: Name of the agent to transfer to
        description: Description of what this agent does
    
    Returns:
        A tool function that delegates with a task description
    """
    name = f"delegate_task_to_{agent_name}"
    description = description or f"Delegate a specific task to {agent_name} agent."
    
    @tool(name, description=description)
    def delegation_tool(
        task_description: Annotated[
            str,
            "Clear description of what the agent should do, including all relevant context from the conversation.",
        ],
        state: Annotated[SupervisorState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Execute task delegation to target agent."""
        # Create a focused message for the worker
        task_message = HumanMessage(content=task_description)
        
        # Update route
        updated_route = state.get("route", []) + [f"supervisor:task_delegated_to:{agent_name}"]
        
        # Create new state with task as the primary message
        worker_state = {
            **state,
            "question": task_description,  # Override question with task
            "messages": [task_message],
            "route": updated_route
        }
        
        return Command(
            goto=agent_name,
            update=worker_state,
            graph=Command.PARENT,
        )
    
    return delegation_tool


# ============================================================================
# Handoff-Back Tool - Workers Return Control to Supervisor
# ============================================================================

def create_handoff_back_tool():
    """
    Create a tool that worker agents can use to return control to the supervisor.
    
    This completes the delegation loop - supervisor delegates to worker,
    worker completes task and hands back to supervisor.
    """
    @tool("transfer_back_to_supervisor", "Transfer control back to the supervisor with results.")
    def handoff_back_tool(
        state: Annotated[SupervisorState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Return control to supervisor."""
        tool_message = {
            "role": "tool",
            "content": "Successfully transferred back to supervisor",
            "name": "transfer_back_to_supervisor",
            "tool_call_id": tool_call_id,
        }
        
        updated_route = state.get("route", []) + ["worker:returned_to_supervisor"]
        
        return Command(
            goto="supervisor",
            update={
                **state,
                "messages": state.get("messages", []) + [tool_message],
                "route": updated_route
            },
            graph=Command.PARENT,
        )
    
    return handoff_back_tool


# ============================================================================
# Supervisor Agent - Central Orchestrator
# ============================================================================

def create_supervisor_node():
    """
    Create a custom supervisor node that routes based on LLM decision.
    
    This is simpler than using create_react_agent and avoids the recursion issues.
    The supervisor makes one LLM call to decide which agent to delegate to,
    then returns a Command to route to that agent.
    
    Returns:
        An async node function for the supervisor
    """
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    
    supervisor_system_prompt = """You are a routing supervisor for a university assistant system.

Your job is to analyze the user's question and decide which specialized agent should handle it.

Available agents:
- **student**: General student info, degree programs, timetables, academic policies, campus facilities
- **faculty**: Faculty directory, professor info, contact details, research areas, office hours
- **exam**: Exam and quiz generation (only for faculty/admin users)
- **obe**: CLO-PLO mapping and outcome alignment
- **direct**: Greetings, small talk, acknowledgments, follow-ups, and general conversation

Respond with ONLY the agent name (student, faculty, exam, obe, or direct) and nothing else.

Examples:
Q: "Who is the rector of FAST?"
A: faculty

Q: "What degree programs are available?"
A: student

Q: "Generate an exam for Computer Networks"
A: exam

Q: "Map CLO1 to PLO2"
A: obe

Q: "Hello"
A: direct

Q: "Thank you"
A: direct

Q: "What can you help me with?"
A: direct"""
    
    async def supervisor_node(state: SupervisorState):
        """Supervisor node that routes to appropriate worker."""
        
        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        route = state.get("route", [])
        
        # Add conversation context for better routing (especially for follow-up questions)
        from ..memory import memory_manager
        context = memory_manager.get_last_context(session_id, last_n=3)
        question_with_context = f"{context}\n{question}" if context else question
        
        # Build messages for LLM
        messages = [
            SystemMessage(content=supervisor_system_prompt),
            HumanMessage(content=f"Question: {question_with_context}")
        ]
        
        # Get LLM decision
        try:
            response = await llm.ainvoke(messages)
            decision = response.content.strip().lower()
        except Exception as e:
            decision = "student"  # Default fallback
        
        # Validate decision
        valid_agents = ["student", "faculty", "exam", "obe", "direct"]
        if decision not in valid_agents:
            decision = "student"
        
        # Update route
        updated_route = route + [f"supervisor:routed_to:{decision}"]
        
        
        # Return Command to navigate to chosen agent
        return Command(
            goto=decision,
            update={
                **state,
                "route": updated_route,
                "messages": state.get("messages", []) + [
                    AIMessage(content=f"Routing to {decision} agent", name="supervisor")
                ]
            }
        )
    
    return supervisor_node


# ============================================================================
# Worker Agent Nodes
# ============================================================================

def create_student_supervisor_wrapper_node():
    """Wrapper that runs the existing compiled student graph and returns state."""
    from ..nodes.student import student_router_node

    async def student_wrapper(state: SupervisorState):
        from ..nodes.student import run_student_streaming

        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        route = state.get("route", [])

        # Optional: include recent context to improve routing
        context = memory_manager.get_last_context(session_id, last_n=10)
        enhanced_q = f"{context}\n{question}" if context else question

        print(f"[STUDENT_SUP] Executing student domain for session={session_id}")
        accumulated = ""
        try:
            for chunk in run_student_streaming(enhanced_q, session_id=session_id):
                accumulated += chunk
                # stream partial
                yield {
                    **state,
                    "result": accumulated,
                    "route": route + ["student_supervisor:streaming"],
                }
        except Exception as e:
            accumulated = f"Error in student domain: {e}"

        updated_route = route + ["student_supervisor:completed"]
        yield {
            **state,
            "result": accumulated,
            "route": updated_route,
            "messages": state.get("messages", []) + [AIMessage(content=accumulated, name="student_supervisor")],
        }

    return student_wrapper


def create_faculty_worker_node():
    """
    Create a node wrapper for the faculty ReAct agent.
    
    The faculty agent is already a ReAct agent with tools, so we configure
    it with session-based memory and wrap for delegation.
    """
    faculty_builder = None
    
    async def faculty_worker(state: SupervisorState):
        """Execute faculty agent and return control to supervisor."""
        nonlocal faculty_builder
        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        route = state.get("route", [])
        
        
        # Add conversation context
        from ..memory import memory_manager
        context = memory_manager.get_last_context(session_id, last_n=20)
        enhanced_question = f"{context}\n{question}" if context else question
        
        # Run faculty agent with session memory and capture streamed tokens
        final_answer = ""
        try:
            if faculty_builder is None:
                faculty_builder = FacultyReactAgentBuilder()
            for token in faculty_builder.stream(enhanced_question, session_id=session_id):
                final_answer += token
        except Exception as e:
            final_answer = f"Error in faculty agent: {e}"
        
        updated_route = route + ["faculty_agent:completed"]
        
        
        return {
            **state,
            "result": final_answer,
            "route": updated_route,
            "messages": state.get("messages", []) + [
                AIMessage(content=final_answer, name="faculty_agent")
            ]
        }
    
    return faculty_worker


def create_exam_worker_node():
    """
    Create a node wrapper for the exam ReAct agent.
    """
    # Lazy initialization
    exam_agent = None
    
    async def exam_worker(state: SupervisorState):
        """Execute exam agent and return control to supervisor."""
        nonlocal exam_agent
        
        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        user_role = state.get("user_role", "student")
        route = state.get("route", [])
        
        
        # Note: exam agent now supports both student and faculty roles with different prompts
        
        # Add conversation context for continuity (similar to faculty agent)
        from ..memory import memory_manager
        context = memory_manager.get_last_context(session_id, last_n=10)
        enhanced_question = f"{context}\n{question}" if context else question
        
        # Initialize agent if needed
        if exam_agent is None:
            exam_agent = ExamReactAgent()
        
        # Stream exam generation with role-aware system prompt internally
        result = ""
        try:
            async for chunk in exam_agent.stream_async(enhanced_question, session_id=session_id, user_role=user_role):
                result += chunk
        except Exception as e:
            result = f"Error in exam agent: {e}"
        
        updated_route = route + ["exam_agent:completed"]
        
        
        return {
            **state,
            "result": result,
            "route": updated_route,
            "messages": state.get("messages", []) + [
                AIMessage(content=result, name="exam_agent")
            ]
        }
    
    return exam_worker


def create_obe_worker_node():
    """
    Create a node wrapper for the OBE agent.
    """
    # Initialize OBE agent
    obe_agent = OBEAgent()
    
    async def obe_worker(state: SupervisorState):
        """Execute OBE agent and return control to supervisor."""
        question = state.get("question", "")
        route = state.get("route", [])
        
        
        # Extract CLOs and PLOs from question
        # Simple extraction - can be enhanced
        import re
        
        clo_pattern = r"CLO[- ]?\d+"
        plo_pattern = r"PLO[- ]?\d+"
        
        clos = re.findall(clo_pattern, question, re.IGNORECASE)
        plos = re.findall(plo_pattern, question, re.IGNORECASE)
        
        
        if not clos or not plos:
            help_msg = (
                "To generate CLO-PLO mappings, please provide:\n"
                "1. Course Learning Outcomes (CLOs)\n"
                "2. Program Learning Outcomes (PLOs)\n\n"
                "Example: 'Map CLO1, CLO2 to PLO1, PLO2, PLO3'"
            )
            return {
                **state,
                "result": help_msg,
                "route": route + ["obe_agent:missing_outcomes"],
                "messages": state.get("messages", []) + [
                    AIMessage(content=help_msg, name="obe_agent")
                ]
            }
        
        # Generate mapping
        try:
            result = obe_agent.run(clos=clos, plos=plos)
        except Exception as e:
            result = f"Error generating OBE mapping: {e}"
        
        updated_route = route + ["obe_agent:completed"]
        
        
        return {
            **state,
            "result": result,
            "route": updated_route,
            "messages": state.get("messages", []) + [
                AIMessage(content=result, name="obe_agent")
            ]
        }
    
    return obe_worker


def create_direct_worker_node():
    """
    Create a node wrapper for handling direct/small talk responses.
    Handles greetings, acknowledgments, general conversation, and questions about conversation history.
    """
    async def direct_worker(state: SupervisorState):
        """Handle small talk and direct responses, including conversation history queries."""
        # Use small_llm to decide and stream assistant-self/small-talk replies, now including history access.
        raw_q = state.get("question", "")
        route = state.get("route", [])
        session_id = state.get("session_id", "default")

        # Retrieve recent conversation history for context (last 10 turns, per conventions)
        from ..memory import memory_manager
        history = memory_manager.get_history(session_id) or []
        recent_turns = history[-10:]  # Limit to last 10 for brevity and performance
        history_context = "\n".join([
            f"User: {turn.user_message}\nAssistant: {turn.agent_response}" for turn in recent_turns
        ]) if recent_turns else "No prior conversation history."

        # Build an expanded system prompt to include history-related queries
        system_prompt = (
            "You are CampusHive's assistant.\n"
            "Role: Provide brief, helpful responses ONLY for:\n"
            "- Greetings, thanks, self-referential questions, or casual small talk.\n"
            "- Questions about the conversation history, such as 'What was my last question?', 'Summarize our chat', or similar meta-queries.\n"
            "Scope: Do NOT attempt to answer domain-specific questions (faculty, student, exam, OBE). If the user's message does not fit the above, respond with the single token: \"NOT_ASSISTANT_SELF\".\n"
            "Behavior: Use the provided conversation history to answer history-related queries accurately and concisely. Keep responses friendly and brief. Stream partial outputs when possible.\n"
            f"Recent Conversation History:\n{history_context}"
        )

        from config import small_llm
        from langchain_core.messages import SystemMessage, HumanMessage

        # Prepare messages with history context
        msgs = [SystemMessage(content=system_prompt), HumanMessage(content=raw_q)]

        # Stream from small_llm; collect partials and check for reroute token
        try:
            partial = ""
            async for chunk in small_llm.astream(msgs):
                text = getattr(chunk, "content", None) or (chunk if isinstance(chunk, str) else "")
                if text is None:
                    continue
                partial += text
                # If the model indicates reroute token, break early
                if "NOT_ASSISTANT_SELF" in partial:
                    break
                # Stream partial to caller
                yield {
                    **state,
                    "result": partial,
                    "route": route + ["direct_agent:streaming"],
                    "messages": state.get("messages", [])
                }

            final = partial.strip()
        except Exception as e:
            # Do not swallow API errors; re-raise per conventions
            raise RuntimeError(f"small_llm error in direct node: {e}") from e

        # If small_llm signaled reroute, provide redirect hint
        if final == "NOT_ASSISTANT_SELF" or "NOT_ASSISTANT_SELF" in final:
            # Check for prior faculty context (unchanged logic)
            prior = None
            for turn in reversed(history):
                for step in reversed(turn.route or []):
                    if "faculty" in step:
                        prior = "faculty"
                        break
                if prior:
                    break
            if prior == "faculty":
                response = (
                    "It looks like you're asking a follow-up about a person. I've routed this to the faculty agent."
                )
                yield {
                    **state,
                    "result": response,
                    "route": route + ["direct_agent:redirect_hint:faculty"],
                    "messages": state.get("messages", []) + [
                        AIMessage(content=response, name="direct_agent")
                    ],
                }
                return

            # Generic fallback
            response = (
                "I'm here to help. If you meant to ask about faculty, students, exams, or learning outcomes, please rephrase or I'll route you to the right team."
            )
            updated_route = route + ["direct_agent:completed"]
            yield {
                **state,
                "result": response,
                "route": updated_route,
                "messages": state.get("messages", []) + [
                    AIMessage(content=response, name="direct_agent")
                ]
            }
            return

        # Otherwise, small_llm produced valid content; return final streamed result
        updated_route = route + ["direct_agent:completed"]
        yield {
            **state,
            "result": final,
            "route": updated_route,
            "messages": state.get("messages", []) + [
                AIMessage(content=final, name="direct_agent")
            ]
        }
        return

    return direct_worker


# ============================================================================
# Build Supervisor Graph with Delegation
# ============================================================================

def build_supervisor_graph():
    """Build hierarchical supervisor graph with domain supervisors.

    Top-level: main_supervisor -> student_supervisor | faculty | exam | direct
    Student domain uses existing compiled student graph via wrapper.
    Faculty domain routes between faculty_info and obe using a small subgraph.
    """

    print("[BUILD] Constructing hierarchical supervisor graph...")

    # Student domain: build subgraph with streaming wrappers
    from .student_supervisor import build_student_graph as build_student_domain
    from ..agent_wrappers.student_wrappers import general_info_node as st_general_node
    from ..agent_wrappers.student_wrappers import timetable_node as st_timetable_node
    from ..agent_wrappers.student_wrappers import degree_advisor_node as st_degree_node

    student_graph = build_student_domain(
        st_general_node(), st_timetable_node(), st_degree_node()
    )
    async def student_supervisor_node(state: dict):
        print("[STUDENT_SUP] Executing student subgraph")
        # Emit a streaming step start
        yield {**state, "result": "", "route": state.get("route", []) + ["student_supervisor:streaming"]}
        out = await student_graph.ainvoke(state)
        r = list(out.get("route", []) or [])
        r.append("student_supervisor:completed")
        out["route"] = r
        msgs = list(out.get("messages", []) or [])
        msgs.append(AIMessage(content="Student subgraph completed", name="student_supervisor"))
        out["messages"] = msgs
        yield out

    # Faculty domain: subgraph routing to faculty_info (react agent) or obe
    faculty_info_node = create_faculty_worker_node()
    obe_node = create_obe_worker_node()
    faculty_graph = build_faculty_graph(faculty_info_node, obe_node)

    # Leaf nodes
    exam_node = create_exam_worker_node()
    direct_node = create_direct_worker_node()

    # Build main graph
    from .main_supervisor import create_main_supervisor_node, build_main_graph
    async def faculty_node_wrapper(state: dict):
        print("[FACULTY_SUP] Executing faculty subgraph")
        # Emit a lightweight streaming step (start)
        yield {**state, "result": "", "route": state.get("route", []) + ["faculty_supervisor:streaming"]}
        out = await faculty_graph.ainvoke(state)
        # Ensure route/message consistency
        try:
            r = list(out.get("route", []) or [])
            r.append("faculty_supervisor:completed")
            out["route"] = r
            msgs = list(out.get("messages", []) or [])
            msgs.append(AIMessage(content="Faculty subgraph completed", name="faculty_supervisor"))
            out["messages"] = msgs
        except Exception:
            pass
        yield out

    main_graph = build_main_graph(
        student_supervisor_node=student_supervisor_node,
        faculty_node=faculty_node_wrapper,
        exam_node=exam_node,
        direct_node=direct_node,
    )

    print("[BUILD] Hierarchical supervisor graph ready.")
    return main_graph


# ============================================================================
# Runner Functions
# ============================================================================

# Build graph once at module level
supervisor_graph = build_supervisor_graph()


async def run_supervisor_async(
    question: str,
    session_id: str = "default",
    user_role: str = "student",
    user_input_mode: bool = False  # True if this is a response to awaiting_user_input
) -> dict:
    """
    Run the supervisor asynchronously with planning support.
    
    Args:
        question: User's question or input
        session_id: Session identifier for conversation memory
        user_role: User's role (student, faculty, admin)
        user_input_mode: True if answering a clarification request
    
    Returns:
        Dict with 'response', 'route', and optionally 'awaiting_user_input', 'scratchpad'
    """
    from .planning_supervisor import get_planning_supervisor
    from .planning_tools import detect_query_complexity
    
    # Load conversation history
    conversation_history = memory_manager.get_history(session_id)
    
    # Check if we should use planning mode
    planning_supervisor = get_planning_supervisor()
    
    # If user is providing input for a pending clarification, use planning mode
    if user_input_mode:
        is_complex = True
    else:
        is_complex = planning_supervisor.detect_complexity(question)
    
    print(f"[SUPERVISOR] Query complexity: {'COMPLEX' if is_complex else 'SIMPLE'}")
    
    # For complex queries, use planning supervisor
    if is_complex:
        # Check if we're resuming from a previous awaiting_user_input state
        # Look for the last state in session memory
        pending_state = None
        if user_input_mode and conversation_history:
            # Try to retrieve pending state from last turn
            # In a proper implementation, we'd store this in a state manager
            # For now, we'll reconstruct minimal state needed to continue
            last_turn = conversation_history[-1] if conversation_history else None
            if last_turn and "__AWAITING_USER_INPUT__" in str(last_turn.get("agent_response", "")):
                # We have a pending state - need to preserve messages and scratchpad
                # This is a limitation: we need to store intermediate state
                # For now, create a new state with the user's response
                pending_state = {
                    "question": question,
                    "session_id": session_id,
                    "user_role": user_role,
                    "route": ["main_supervisor:resuming_from_input"],
                    "result": "",
                    "conversation_history": conversation_history,
                    "messages": [],  # Will be populated by planning supervisor
                    "scratchpad": [f"[User Response] {question}"],
                    "planning_mode": True,
                }
        
        if not pending_state:
            # New complex query
            planning_state = {
                "question": question,
                "session_id": session_id,
                "user_role": user_role,
                "route": [],
                "result": "",
                "conversation_history": conversation_history,
                "messages": [HumanMessage(content=question)],
                "scratchpad": [],
                "plan": [],
                "current_task_id": 0,
                "intermediate_results": {},
                "awaiting_user_input": False,
                "user_input_question": "",
                "user_input_context": {},
                "planning_mode": True,
                "max_retries": 3,
                "total_api_calls": 0
            }
        else:
            planning_state = pending_state
        
        try:
            # Execute with resume flag if in user_input_mode
            result_state = await planning_supervisor.execute_complex(
                planning_state, 
                resume_from_input=user_input_mode
            )
            
            # Check if we need user input
            if result_state.get("awaiting_user_input"):
                # Don't store in memory yet - waiting for user input
                return {
                    "response": result_state.get("user_input_question", "I need more information."),
                    "awaiting_user_input": True,
                    "scratchpad": result_state.get("scratchpad", []),
                    "route": result_state.get("route", []),
                    "planning_mode": True
                }
            
            # Store in memory
            final_result = result_state.get("result", "")
            final_route = result_state.get("route", [])
            memory_manager.add_turn(session_id, question, final_result, final_route)
            
            return {
                "response": final_result,
                "result": final_result,
                "route": final_route,
                "scratchpad": result_state.get("scratchpad", []),
                "planning_mode": True,
                "awaiting_user_input": False
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            error_msg = f"Error in planning mode: {str(e)}"
            return {
                "response": error_msg,
                "route": ["error:planning_mode"],
                "planning_mode": True
            }
    
    # For simple queries, use fast path (existing hierarchical routing)
    # Build initial state
    initial_state = {
        "question": question,
        "session_id": session_id,
        "user_role": user_role,
        "route": [],
        "result": "",
        "conversation_history": conversation_history,
        "messages": [HumanMessage(content=question)]
    }
    
    
    final_result = ""
    final_route = []
    
    try:
        # Stream through graph with increased recursion limit
        # The supervisor ReAct agent may need multiple reasoning steps
        config = {"recursion_limit": 50}
        
        
        event_count = 0
        async for event in supervisor_graph.astream(initial_state, config=config):
            event_count += 1

            # Capture results; consider new node names
            for node_name in ["student_supervisor", "faculty", "exam", "direct"]:
                if node_name in event:
                    node_output = event[node_name]
                    if isinstance(node_output, dict) and "result" in node_output:
                        # Only accept non-empty results to avoid clobbering a real
                        # response with intermediate empty streaming steps.
                        res = node_output.get("result", "")
                        if res:
                            final_result = res
                            final_route = node_output.get("route", final_route)
            

    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "response": f"Error in supervisor delegation: {e}",
            "route": ["error"]
        }
    
    # Fallback if no result
    if not final_result:
        final_result = "I apologize, but I couldn't process your request. Please try again."
    
    # Store in memory
    memory_manager.add_turn(session_id, question, final_result, final_route)
    
    
    return {
        "response": final_result,
        "result": final_result,  # backward-compatible key used by some callers
        "route": final_route
    }


def run_supervisor(
    question: str,
    session_id: str = "default",
    user_role: str = "student"
) -> dict:
    """
    Synchronous wrapper for supervisor.
    
    Args:
        question: User's question
        session_id: Session identifier
        user_role: User's role
    
    Returns:
        Dict with 'response' and 'route'
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Use thread pool if already in async context
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    run_supervisor_async(question, session_id, user_role)
                )
                return future.result()
        else:
            return asyncio.run(
                run_supervisor_async(question, session_id, user_role)
            )
    except Exception as e:
        return {
            "response": f"Error: {e}",
            "route": ["error"]
        }
