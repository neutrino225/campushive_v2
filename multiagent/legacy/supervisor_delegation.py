"""
DEPRECATED: This file has been moved to multiagent/legacy/supervisor_delegation.py
and remains here temporarily for backward compatibility during migration.

Multi-Agent Supervisor with Delegation Pattern
Based on LangGraph's agent_supervisor tutorial pattern.

The supervisor is itself a ReAct agent that delegates work to specialized worker agents
using handoff tools. This provides better control flow and natural task delegation.
"""
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

Respond with ONLY the agent name (student, faculty, exam, or obe) and nothing else.

Examples:
Q: "Who is the rector of FAST?"
A: faculty

Q: "What degree programs are available?"
A: student

Q: "Generate an exam for Computer Networks"
A: exam

Q: "Map CLO1 to PLO2"
A: obe"""
    
    async def supervisor_node(state: SupervisorState):
        """Supervisor node that routes to appropriate worker."""
        print(f"\n🎯 SUPERVISOR NODE: Analyzing question...")
        
        question = state.get("question", "")
        route = state.get("route", [])
        
        print(f"   Question: {question[:100]}...")
        
        # Build messages for LLM
        messages = [
            SystemMessage(content=supervisor_system_prompt),
            HumanMessage(content=f"Question: {question}")
        ]
        
        # Get LLM decision
        print(f"   Calling LLM for routing decision...")
        try:
            response = await llm.ainvoke(messages)
            decision = response.content.strip().lower()
            print(f"   ✅ LLM Decision: '{decision}'")
        except Exception as e:
            print(f"   ❌ LLM Error: {e}")
            decision = "student"  # Default fallback
        
        # Validate decision
        valid_agents = ["student", "faculty", "exam", "obe"]
        if decision not in valid_agents:
            print(f"   ⚠️  Invalid decision '{decision}', defaulting to 'student'")
            decision = "student"
        
        # Update route
        updated_route = route + [f"supervisor:routed_to:{decision}"]
        
        print(f"   🔀 Routing to '{decision}' agent")
        print(f"   Updated route: {' -> '.join(updated_route)}")
        
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

def create_student_worker_node():
    """
    Create a node wrapper for the student agent subgraph.
    
    The student agent handles general queries, degree programs, and timetables.
    It's already a complex subgraph, so we wrap it for the delegation pattern.
    """
    from ..nodes.student import run_student_streaming
    
    async def student_worker(state: SupervisorState):
        """Execute student agent and return control to supervisor."""
        print(f"\n📚 STUDENT WORKER: Starting execution")
        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        route = state.get("route", [])
        
        print(f"   Question: {question[:100]}...")
        
        # Get conversation context
        from ..memory import memory_manager
        context = memory_manager.get_last_context(session_id, last_n=20)
        enhanced_question = f"{context}\n{question}" if context else question
        
        # Stream response from student agent
        print(f"   Streaming from student subgraph...")
        result = ""
        try:
            async for chunk in run_student_streaming(enhanced_question, session_id=session_id):
                result += chunk
        except Exception as e:
            print(f"   ❌ Error in student agent: {e}")
            result = f"Error in student agent: {e}"
        
        # Update state with results
        updated_route = route + ["student_agent:completed"]
        
        print(f"   ✅ Student worker completed")
        print(f"   Response length: {len(result)} chars")
        print(f"   Response preview: {result[:150]}...")
        
        return {
            **state,
            "result": result,
            "route": updated_route,
            "messages": state.get("messages", []) + [
                AIMessage(content=result, name="student_agent")
            ]
        }
    
    return student_worker


def create_faculty_worker_node():
    """
    Create a node wrapper for the faculty ReAct agent.
    
    The faculty agent is already a ReAct agent with tools, so we configure
    it with session-based memory and wrap for delegation.
    """
    # Build faculty agent once
    print("   🔧 Building faculty ReAct agent...")
    faculty_builder = FacultyReactAgentBuilder()
    faculty_agent = faculty_builder.get_agent()
    print("   ✅ Faculty agent ready")
    
    async def faculty_worker(state: SupervisorState):
        """Execute faculty agent and return control to supervisor."""
        print(f"\n👨‍🏫 FACULTY WORKER: Starting execution")
        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        route = state.get("route", [])
        
        print(f"   Question: {question[:100]}...")
        
        # Add conversation context
        from ..memory import memory_manager
        context = memory_manager.get_last_context(session_id, last_n=20)
        enhanced_question = f"{context}\n{question}" if context else question
        
        # Run faculty agent with session memory
        config_dict = {"configurable": {"thread_id": f"faculty_react::{session_id}"}}
        final_answer = ""
        
        print(f"   Running faculty ReAct agent...")
        try:
            for step in faculty_agent.stream(
                {"messages": [{"type": "human", "content": enhanced_question}]},
                config_dict,
                stream_mode="values",
            ):
                if step.get("messages"):
                    last_msg = step["messages"][-1]
                    if hasattr(last_msg, "content") and isinstance(last_msg.content, str):
                        final_answer = last_msg.content
                        print(f"   📝 Got message: {last_msg.content[:100]}...")
        except Exception as e:
            print(f"   ❌ Error in faculty agent: {e}")
            final_answer = f"Error in faculty agent: {e}"
        
        updated_route = route + ["faculty_agent:completed"]
        
        print(f"   ✅ Faculty worker completed")
        print(f"   Response length: {len(final_answer)} chars")
        print(f"   Response preview: {final_answer[:150]}...")
        
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
        
        print(f"\n📝 EXAM WORKER: Starting execution")
        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        user_role = state.get("user_role", "student")
        route = state.get("route", [])
        
        print(f"   Question: {question[:100]}...")
        print(f"   User role: {user_role}")
        
        # Authorization check
        if user_role not in ["faculty", "admin"]:
            print(f"   ❌ Unauthorized: User role '{user_role}' cannot generate exams")
            unauthorized_msg = "Exam generation is only available to faculty and admin users."
            return {
                **state,
                "result": unauthorized_msg,
                "route": route + ["exam_agent:unauthorized"],
                "messages": state.get("messages", []) + [
                    AIMessage(content=unauthorized_msg, name="exam_agent")
                ]
            }
        
        # Initialize agent if needed
        if exam_agent is None:
            print(f"   🔧 Initializing exam agent...")
            exam_agent = ExamReactAgent()
        
        # Stream exam generation
        print(f"   Generating exam...")
        result = ""
        try:
            async for chunk in exam_agent.stream_async(question, session_id=session_id, user_role=user_role):
                result += chunk
        except Exception as e:
            print(f"   ❌ Error in exam agent: {e}")
            result = f"Error in exam agent: {e}"
        
        updated_route = route + ["exam_agent:completed"]
        
        print(f"   ✅ Exam worker completed")
        print(f"   Response length: {len(result)} chars")
        
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
    print("   🔧 Initializing OBE agent...")
    obe_agent = OBEAgent()
    print("   ✅ OBE agent ready")
    
    async def obe_worker(state: SupervisorState):
        """Execute OBE agent and return control to supervisor."""
        print(f"\n🎯 OBE WORKER: Starting execution")
        question = state.get("question", "")
        route = state.get("route", [])
        
        print(f"   Question: {question[:100]}...")
        
        # Extract CLOs and PLOs from question
        # Simple extraction - can be enhanced
        import re
        
        clo_pattern = r"CLO[- ]?\d+"
        plo_pattern = r"PLO[- ]?\d+"
        
        clos = re.findall(clo_pattern, question, re.IGNORECASE)
        plos = re.findall(plo_pattern, question, re.IGNORECASE)
        
        print(f"   Found CLOs: {clos}")
        print(f"   Found PLOs: {plos}")
        
        if not clos or not plos:
            print(f"   ⚠️  Missing CLOs or PLOs")
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
        print(f"   Generating OBE mapping...")
        try:
            result = obe_agent.run(clos=clos, plos=plos)
            print(f"   ✅ OBE mapping generated")
        except Exception as e:
            print(f"   ❌ Error generating mapping: {e}")
            result = f"Error generating OBE mapping: {e}"
        
        updated_route = route + ["obe_agent:completed"]
        
        print(f"   Response length: {len(result)} chars")
        
        return {
            **state,
            "result": result,
            "route": updated_route,
            "messages": state.get("messages", []) + [
                AIMessage(content=result, name="obe_agent")
            ]
        }
    
    return obe_worker


# ============================================================================
# Build Supervisor Graph with Delegation
# ============================================================================

def build_supervisor_delegation_graph():
    """
    Build the multi-agent supervisor graph using the delegation pattern.
    
    Graph structure:
    - START -> supervisor (custom routing node)
    - supervisor -> worker agents (via Command.goto)
    - worker agents -> END (complete after execution)
    
    The supervisor is a simple node that uses one LLM call to decide routing,
    avoiding the recursion issues of nested ReAct agents.
    
    Returns:
        Compiled LangGraph graph
    """
    print("\n🏗️  Building supervisor delegation graph...")
    
    graph = StateGraph(SupervisorState)
    
    # Create supervisor node (simple LLM-based router)
    print("   Creating supervisor node...")
    supervisor = create_supervisor_node()
    
    # Create worker nodes
    print("   Creating worker nodes...")
    student_worker = create_student_worker_node()
    faculty_worker = create_faculty_worker_node()
    exam_worker = create_exam_worker_node()
    obe_worker = create_obe_worker_node()
    
    # Add nodes to graph
    print("   Adding nodes to graph...")
    graph.add_node("supervisor", supervisor)
    graph.add_node("student", student_worker)
    graph.add_node("faculty", faculty_worker)
    graph.add_node("exam", exam_worker)
    graph.add_node("obe", obe_worker)
    
    # Set entry point
    graph.set_entry_point("supervisor")
    
    # Add edges: workers go directly to END after completion
    graph.add_edge("student", END)
    graph.add_edge("faculty", END)
    graph.add_edge("exam", END)
    graph.add_edge("obe", END)
    
    print("   ✅ Graph structure complete")
    print("   Compiling graph...")
    
    # Compile the graph
    compiled = graph.compile()
    
    print("   ✅ Graph compiled successfully\n")
    
    return compiled


# ============================================================================
# Runner Functions
# ============================================================================

# Build graph once at module level
supervisor_delegation_graph = build_supervisor_delegation_graph()


async def run_supervisor_delegation_async(
    question: str,
    session_id: str = "default",
    user_role: str = "student"
) -> dict:
    """
    Run the delegation-based supervisor asynchronously.
    
    Args:
        question: User's question
        session_id: Session identifier for conversation memory
        user_role: User's role (student, faculty, admin)
    
    Returns:
        Dict with 'response' and 'route' keys
    """
    print(f"\n{'='*80}")
    print(f"🚀 STARTING DELEGATION SUPERVISOR")
    print(f"{'='*80}")
    print(f"Question: {question}")
    print(f"Session: {session_id}")
    print(f"User Role: {user_role}")
    
    # Load conversation history
    conversation_history = memory_manager.get_history(session_id)
    print(f"Conversation history: {len(conversation_history)} turns")
    
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
    
    print(f"\n📋 Initial state prepared")
    print(f"   State keys: {list(initial_state.keys())}")
    
    final_result = ""
    final_route = []
    
    try:
        # Stream through graph with increased recursion limit
        # The supervisor ReAct agent may need multiple reasoning steps
        config = {"recursion_limit": 50}
        
        print(f"\n🔄 Starting graph stream (recursion_limit=50)...")
        
        event_count = 0
        async for event in supervisor_delegation_graph.astream(initial_state, config=config):
            event_count += 1
            print(f"\n📦 Event {event_count}: {list(event.keys())}")
            
            # Get last result from any worker node
            for node_name in ["student", "faculty", "exam", "obe"]:
                if node_name in event:
                    print(f"   ✅ Found output from '{node_name}' worker")
                    node_output = event[node_name]
                    if "result" in node_output:
                        final_result = node_output["result"]
                        final_route = node_output.get("route", [])
                        print(f"   Result captured: {len(final_result)} chars")
                        print(f"   Route: {' -> '.join(final_route)}")
            
            # Also check supervisor events
            if "supervisor" in event:
                print(f"   🎯 Supervisor event")
                supervisor_output = event["supervisor"]
                if "messages" in supervisor_output:
                    messages = supervisor_output["messages"]
                    print(f"   Messages count: {len(messages)}")
                    if messages:
                        # Show last few messages to see tool calls
                        for i, msg in enumerate(messages[-5:], start=len(messages)-4):
                            msg_type = type(msg).__name__
                            print(f"      Message {i}: {msg_type}")
                            if hasattr(msg, "content"):
                                print(f"         Content: {str(msg.content)[:80]}...")
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                print(f"         Tool calls: {len(msg.tool_calls)}")
                                for tc in msg.tool_calls:
                                    print(f"            - {tc.get('name', 'unknown')}")
        
        print(f"\n✅ Graph stream completed. Total events: {event_count}")
    
    except Exception as e:
        print(f"\n❌ ERROR in delegation: {e}")
        import traceback
        traceback.print_exc()
        return {
            "response": f"Error in supervisor delegation: {e}",
            "route": ["error"]
        }
    
    # Fallback if no result
    if not final_result:
        print(f"\n⚠️  No result captured from workers")
        final_result = "I apologize, but I couldn't process your request. Please try again."
    else:
        print(f"\n✅ Final result: {len(final_result)} chars")
    
    # Store in memory
    print(f"💾 Storing conversation turn in memory...")
    memory_manager.add_turn(session_id, question, final_result, final_route)
    
    print(f"\n{'='*80}")
    print(f"🎉 DELEGATION COMPLETE")
    print(f"{'='*80}\n")
    
    return {
        "response": final_result,
        "route": final_route
    }


def run_supervisor_delegation(
    question: str,
    session_id: str = "default",
    user_role: str = "student"
) -> dict:
    """
    Synchronous wrapper for delegation-based supervisor.
    
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
                    run_supervisor_delegation_async(question, session_id, user_role)
                )
                return future.result()
        else:
            return asyncio.run(
                run_supervisor_delegation_async(question, session_id, user_role)
            )
    except Exception as e:
        return {
            "response": f"Error: {e}",
            "route": ["error"]
        }
