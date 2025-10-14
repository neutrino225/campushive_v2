"""
Planning-based main supervisor with ReAct reasoning and scratchpad.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Annotated

root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langgraph.prebuilt import create_react_agent, InjectedState
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.types import Command

from config import llm
from multiagent.memory import memory_manager
from .planning_state import PlanningState, SubTask
from .planning_tools import detect_query_complexity, request_user_input


class PlanningMainSupervisor:
    """
    Main supervisor with planning capabilities.
    
    For simple queries: Routes directly to appropriate agent
    For complex queries: Creates a plan, executes steps, handles human-in-the-loop
    """
    
    def __init__(self):
        """Initialize the planning supervisor."""
        self.checkpointer = MemorySaver()
        self._build_tools()
        self._build_agent()
    
    def _build_tools(self):
        """Build tools for delegation to domain supervisors and agents."""
        
        @tool
        def query_student_domain(
            query: Annotated[str, "Question to ask the student domain (degrees, courses, timetables)"],
            state: Annotated[dict, InjectedState]
        ) -> str:
            """
            Delegate to student domain for questions about degree programs, courses, 
            admissions, timetables, academic policies, and campus facilities.
            
            The student domain will intelligently route to:
            - General info agent
            - Timetable agent  
            - Degree advisor agent
            
            Args:
                query: The specific question to ask
                state: Injected state
            
            Returns:
                Answer from student domain
            """
            from .student_supervisor import build_student_graph
            from ..agent_wrappers.student_wrappers import (
                general_info_node, timetable_node, degree_advisor_node
            )
            
            # Build student graph
            student_graph = build_student_graph(
                general_info_node(), timetable_node(), degree_advisor_node()
            )
            
            # Prepare state
            session_id = state.get("session_id", "default")
            student_state = {
                "question": query,
                "session_id": session_id,
                "route": [],
                "result": "",
                "conversation_history": state.get("conversation_history", []),
                "user_role": state.get("user_role", "student"),
                "messages": [HumanMessage(content=query)]
            }
            
            try:
                # Execute student graph
                result = student_graph.invoke(student_state)
                return result.get("result", "No result from student domain")
            except Exception as e:
                return f"Error in student domain: {str(e)}"
        
        @tool
        def query_faculty_domain(
            query: Annotated[str, "Question to ask the faculty domain (faculty info, OBE mappings)"],
            state: Annotated[dict, InjectedState]
        ) -> str:
            """
            Delegate to faculty domain for questions about faculty members,
            professors, contact information, and OBE/CLO-PLO mappings.
            
            Args:
                query: The specific question to ask
                state: Injected state
            
            Returns:
                Answer from faculty domain
            """
            from ..agents.faculty_react_agent import FacultyReactAgentBuilder
            
            session_id = state.get("session_id", "default")
            context = memory_manager.get_last_context(session_id, last_n=3)
            enhanced_query = f"{context}\n{query}" if context else query
            
            try:
                builder = FacultyReactAgentBuilder()
                result = ""
                for token in builder.stream(enhanced_query, session_id=session_id):
                    result += token
                return result if result else "No result from faculty domain"
            except Exception as e:
                return f"Error in faculty domain: {str(e)}"
        
        @tool
        def query_exam_domain(
            query: Annotated[str, "Request to generate exams or quizzes"],
            state: Annotated[dict, InjectedState]
        ) -> str:
            """
            Delegate to exam domain for generating exams, quizzes, and assessments.
            
            This agent can:
            - Generate complete exams (Final, Sessional, Midterm)
            - Create custom assessments with specific requirements
            - Adapt to flexible time limits and mark distributions
            - Remember context from previous exam requests for modifications
            
            Args:
                query: The exam generation request (include course, marks, time, etc.)
                state: Injected state
            
            Returns:
                Generated exam content
            """
            from ..agents.exam_react_agent import ExamReactAgent
            
            session_id = state.get("session_id", "default")
            user_role = state.get("user_role", "student")
            
            # Include conversation context for follow-up modifications
            context = memory_manager.get_last_context(session_id, last_n=10)
            enhanced_query = f"{context}\n{query}" if context else query
            
            try:
                agent = ExamReactAgent()
                result = ""
                # Use sync stream for tool context (async would require different handling)
                for chunk in agent.stream(enhanced_query, session_id=session_id, user_role=user_role):
                    result += chunk
                return result if result else "No result from exam domain"
            except Exception as e:
                return f"Error in exam domain: {str(e)}"
        
        @tool
        def request_clarification(
            question: Annotated[str, "Question to ask the user"],
            reason: Annotated[str, "Why you need this information"],
            state: Annotated[dict, InjectedState]
        ) -> str:
            """
            Ask the user for clarification or additional information.
            
            Use this when you need user-specific details to proceed, such as:
            - Which electives they chose
            - Their current semester
            - Preferences or constraints
            
            The system will pause and wait for user response.
            
            Args:
                question: Clear question to ask
                reason: Explanation of why you need this
                state: Injected state
            
            Returns:
                Signal to pause execution
            """
            # This is a special return value that the graph will detect
            return f"__AWAITING_USER_INPUT__|{question}|{reason}"
        
        self.tools = [
            query_student_domain,
            query_faculty_domain,
            query_exam_domain,
            request_clarification
        ]
    
    def _build_agent(self):
        """Build the ReAct agent with planning capabilities."""
        
        system_prompt = """You are CampusHive's main supervisor - an intelligent planning agent for FAST-NUCES (National University of Computer and Emerging Sciences), Islamabad campus.

**Your Role:**
You coordinate multiple specialized domains to answer user queries. For complex queries, you break them down into steps, delegate to appropriate agents, and synthesize results.

**Available Domains (via tools):**
1. **query_student_domain**: ALL university-related questions including:
   - Degree programs and their course structures (semester-wise courses for BS CS, BS AI, etc.)
   - Course information, prerequisites, credit hours
   - Admissions, eligibility, application process
   - Timetables and schedules (when available)
   - Academic policies, facilities, scholarships
   - General university information
   
2. **query_faculty_domain**: Faculty-specific information:
   - Professor details, contact information
   - Research interests and publications
   - OBE/CLO-PLO mappings for courses
   
3. **query_exam_domain**: Exam and assessment generation:
   - Generate exams, quizzes, assessments
   - Supports flexible formats (marks, time limits, question types)
   - Remembers context for modifications ("make it harder", "add more questions")
   
4. **request_clarification**: User input:
   - Ask user for additional information when needed
   - Use when you need user-specific details (electives chosen, section, preferences)

**CRITICAL RULES:**
- For ANY question about FAST-NUCES (courses, programs, admissions, etc.) → Use query_student_domain
- NEVER use external web search for university data - all data is in the student domain
- The student domain will route internally to the best agent (general_info/degree_advisor/timetable)

**Approach for SIMPLE queries:**
- Use ONE tool call to get the answer
- Return the result directly

**Approach for COMPLEX queries** (multiple steps, user-specific context):
1. **Analyze**: Break down what information you need
2. **Plan**: Determine the sequence of tool calls
3. **Execute**: Call tools one by one, building on previous results
4. **Clarify**: Use request_clarification if you need user-specific details
5. **Synthesize**: Combine results into a complete answer

**Important Guidelines:**
- Think step-by-step for complex queries
- Request clarification IMMEDIATELY when you realize you need user-specific information
- Don't make assumptions about user preferences (electives, sections, etc.)
- **After receiving user input, CONTINUE your plan** - don't just echo their response
- When you get user information, immediately use it in your next tool call
- Be concise but thorough
- If a tool fails, try a different approach (max 3 retries per subtask)

**Examples:**

*Simple Query:*
User: "Who is the rector of FAST?"
You: [Use query_faculty_domain once] → Return answer

*Simple Exam Query:*
User: "Generate a final exam for Computer Networks with 5 questions, worth 50 marks"
You: [Use query_exam_domain with the full request] → Return generated exam

*Follow-up Query (Context-Aware):*
User: "Build this final worth 50 marks but it will be taken in time limit of 180 minutes so the questions should be long"
You: [query_exam_domain: "Build this final worth 50 marks but it will be taken in time limit of 180 minutes so the questions should be long"]
Note: The exam domain remembers the previous exam request and will apply modifications

*Complex Query with User Input (Timetable):*
User: "I'm a 7th semester BS AI student, give me my complete timetable"
You: 
1. [request_clarification: "Which elective courses have you selected for your 7th semester?"]
[System pauses, user responds: "Agentic AI, OBL, and Reinforcement Learning"]
2. [RESUME] Now I know the user's electives
3. [query_student_domain: "I'm a 7th semester BS AI student. My electives are: Agentic AI, OBL, and Reinforcement Learning. Give me my complete timetable with class schedules."]
4. Return the complete answer from the student domain (which will route to timetable agent)

**CRITICAL:** Do NOT try to handle timetable fallbacks yourself. The timetable agent will provide appropriate responses based on data availability. Just delegate and return its response.

**CRITICAL: After receiving user input via request_clarification:**
- DO NOT just echo back their response
- IMMEDIATELY continue with your next tool call using the new information
- Complete the original task the user requested
- Trust the domain agents to handle their own responses completely

**Context Awareness:**
- All domain tools have access to conversation history through memory_manager
- When users say "it", "that exam", "the program", etc., the tools can reference previous context
- Always pass the FULL user query to tools (don't paraphrase) to preserve pronouns and references

Remember: Your reasoning process is visible to users, so think clearly and explain your steps!"""

        self.agent = create_react_agent(
            model=llm,
            tools=self.tools,
            checkpointer=self.checkpointer,
            prompt=system_prompt
        )
    
    def detect_complexity(self, question: str) -> bool:
        """Detect if query needs planning mode."""
        return detect_query_complexity(question)
    
    async def execute_simple(self, state: PlanningState) -> Dict[str, Any]:
        """
        Execute simple query without planning overhead.
        Fast path for straightforward questions.
        """
        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        
        # Add conversation context
        context = memory_manager.get_last_context(session_id, last_n=3)
        enhanced_q = f"{context}\n{question}" if context else question
        
        messages = [HumanMessage(content=enhanced_q)]
        config = {"configurable": {"thread_id": f"planning_main::{session_id}"}}
        
        try:
            # Single-shot execution
            result_state = await self.agent.ainvoke(
                {"messages": messages},
                config
            )
            
            # Extract final message
            if result_state.get("messages"):
                last_msg = result_state["messages"][-1]
                result = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
            else:
                result = "No response generated"
            
            return {
                **state,
                "result": result,
                "route": state.get("route", []) + ["main_supervisor:simple_mode"],
                "planning_mode": False
            }
            
        except Exception as e:
            return {
                **state,
                "result": f"Error: {str(e)}",
                "route": state.get("route", []) + ["main_supervisor:error"],
                "planning_mode": False
            }
    
    async def execute_complex(self, state: PlanningState, resume_from_input: bool = False) -> Dict[str, Any]:
        """
        Execute complex query with full planning and scratchpad.
        
        Args:
            state: Current planning state
            resume_from_input: True if resuming after user provided input
        """
        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        
        # Initialize or continue scratchpad
        scratchpad = state.get("scratchpad", [])
        if not scratchpad:
            scratchpad = [f"[Planning Mode] Analyzing complex query: {question}"]
        
        config = {"configurable": {"thread_id": f"planning_main::{session_id}"}}
        
        # If resuming, get the current state from checkpointer and add user message
        if resume_from_input:
            try:
                # Get current state from checkpointer
                current_state = await self.agent.aget_state(config)
                existing_messages = current_state.values.get("messages", [])
                
                # Add user's response as a new message
                scratchpad.append(f"[User provided] {question}")
                
                # Build the complete message history for continuation
                # The user's response should be treated as input to the agent
                messages_for_continuation = existing_messages + [HumanMessage(content=question)]
                
                print(f"[PLANNING_RESUME] Continuing with {len(messages_for_continuation)} messages")
                print(f"[PLANNING_RESUME] User provided: {question}")
                
                # Continue execution with the updated messages
                # Instead of using aupdate_state + astream(None), we invoke with the full message list
                final_result = ""
                agent_messages = []
                
                async for event in self.agent.astream(
                    {"messages": messages_for_continuation},  # Pass updated messages directly
                    config,
                    stream_mode="values"
                ):
                    if event.get("messages"):
                        agent_messages = event["messages"]
                        last_msg = agent_messages[-1]
                        
                        # Check for another user input request
                        if hasattr(last_msg, "content") and "__AWAITING_USER_INPUT__" in str(last_msg.content):
                            parts = last_msg.content.split("|")
                            if len(parts) >= 3:
                                return {
                                    **state,
                                    "awaiting_user_input": True,
                                    "user_input_question": parts[1],
                                    "user_input_context": {"reason": parts[2]},
                                    "scratchpad": scratchpad,
                                    "messages": agent_messages,
                                    "route": state.get("route", []) + ["main_supervisor:awaiting_input"],
                                    "planning_mode": True
                                }
                        
                        # Only capture AI responses as final result, not user messages or tool outputs
                        if hasattr(last_msg, "content") and hasattr(last_msg, "__class__"):
                            msg_type = last_msg.__class__.__name__
                            if msg_type == "AIMessage" and not str(last_msg.content).startswith("__"):
                                final_result = last_msg.content
                
                # Extract scratchpad updates from tool calls
                for msg in agent_messages:
                    if hasattr(msg, "additional_kwargs") and msg.additional_kwargs.get("tool_calls"):
                        for tool_call in msg.additional_kwargs["tool_calls"]:
                            tool_name = tool_call.get("function", {}).get("name", "unknown")
                            scratchpad.append(f"[Action] Calling {tool_name}")
                
                # Ensure we have a meaningful result
                if not final_result or final_result.strip() == question.strip():
                    # Agent didn't produce output, might be still processing
                    print(f"[PLANNING_RESUME] WARNING: No meaningful result. final_result='{final_result}'")
                    print(f"[PLANNING_RESUME] Total messages in conversation: {len(agent_messages)}")
                    scratchpad.append("[Warning] No final AI response captured, agent may need more steps")
                    final_result = "I'm processing your request. Please wait..."
                else:
                    print(f"[PLANNING_RESUME] SUCCESS: Got result with {len(final_result)} chars")
                
                return {
                    **state,
                    "result": final_result,
                    "scratchpad": scratchpad,
                    "messages": agent_messages,
                    "route": state.get("route", []) + ["main_supervisor:resumed_and_completed"],
                    "planning_mode": True,
                    "awaiting_user_input": False
                }
                
            except Exception as e:
                scratchpad.append(f"[Error resuming] {str(e)}")
                # Fall back to new conversation
                resume_from_input = False
        
        # New conversation or fallback from resume error
        if not resume_from_input:
            messages = [HumanMessage(content=question)]
            
            try:
                # Stream through agent execution to capture reasoning
                final_result = ""
                agent_messages = []
                
                async for event in self.agent.astream(
                    {"messages": messages},
                    config,
                    stream_mode="values"
                ):
                    if event.get("messages"):
                        agent_messages = event["messages"]
                        last_msg = agent_messages[-1]
                        
                        # Check for user input request
                        if hasattr(last_msg, "content") and "__AWAITING_USER_INPUT__" in str(last_msg.content):
                            parts = last_msg.content.split("|")
                            if len(parts) >= 3:
                                return {
                                    **state,
                                    "awaiting_user_input": True,
                                    "user_input_question": parts[1],
                                    "user_input_context": {"reason": parts[2]},
                                    "scratchpad": scratchpad,
                                    "messages": agent_messages,  # Preserve conversation state
                                    "route": state.get("route", []) + ["main_supervisor:awaiting_input"],
                                    "planning_mode": True
                                }
                        
                        # Capture content
                        if hasattr(last_msg, "content"):
                            final_result = last_msg.content
                
                # Extract scratchpad from agent messages (tool calls, thoughts)
                for msg in agent_messages:
                    if hasattr(msg, "additional_kwargs") and msg.additional_kwargs.get("tool_calls"):
                        for tool_call in msg.additional_kwargs["tool_calls"]:
                            tool_name = tool_call.get("function", {}).get("name", "unknown")
                            scratchpad.append(f"[Action] Calling {tool_name}")
                
                return {
                    **state,
                    "result": final_result,
                    "scratchpad": scratchpad,
                    "messages": agent_messages,
                    "route": state.get("route", []) + ["main_supervisor:planning_mode_complete"],
                    "planning_mode": True,
                    "awaiting_user_input": False
                }
                
            except Exception as e:
                scratchpad.append(f"[Error] {str(e)}")
                return {
                    **state,
                    "result": f"Error in planning mode: {str(e)}",
                    "scratchpad": scratchpad,
                    "route": state.get("route", []) + ["main_supervisor:error"],
                    "planning_mode": True
                }


# Global instance
_planning_supervisor = None

def get_planning_supervisor() -> PlanningMainSupervisor:
    """Get or create the planning supervisor instance."""
    global _planning_supervisor
    if _planning_supervisor is None:
        _planning_supervisor = PlanningMainSupervisor()
    return _planning_supervisor
