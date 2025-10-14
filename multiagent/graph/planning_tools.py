"""
Tools for the planning-based main supervisor.
"""

import sys
from pathlib import Path
from typing import Annotated

root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


@tool
def request_user_input(
    question: Annotated[str, "The question to ask the user"],
    context: Annotated[str, "Context about why this information is needed"],
    state: Annotated[dict, InjectedState]
) -> str:
    """
    Request input from the user during execution.
    
    Use this when you need additional information from the user to proceed.
    The system will pause execution and wait for user response.
    
    Args:
        question: Clear question to ask the user
        context: Explanation of why you need this information
        state: Injected graph state
    
    Returns:
        Instruction to use the user's next message as input
    """
    # Signal that we're waiting for input via special marker
    # The planning supervisor will detect this and interrupt execution
    return f"__AWAITING_USER_INPUT__|{question}|{context}"


@tool
def add_to_scratchpad(
    thought: Annotated[str, "Your current thinking/reasoning"],
    state: Annotated[dict, InjectedState]
) -> str:
    """
    Add a thought to your scratchpad.
    
    Use this to record your reasoning process. The scratchpad is visible to users.
    
    Args:
        thought: Your current reasoning or observation
        state: Injected graph state
    
    Returns:
        Confirmation
    """
    scratchpad = state.get("scratchpad", [])
    scratchpad.append(thought)
    return f"Added to scratchpad: {thought[:100]}..."


def detect_query_complexity(question: str, conversation_history: list = None) -> bool:
    """
    Detect if a query requires planning or can be answered directly using small_llm.
    
    Complex queries involve:
    - Multiple steps or information gathering
    - Conditional logic (if X then Y)
    - User-specific context that needs clarification
    - Aggregation from multiple sources
    
    Simple queries:
    - Direct factual questions
    - Single-agent lookup
    - Greetings/small talk
    - Follow-up questions with clear context
    
    Args:
        question: User's question
        conversation_history: Recent conversation turns
    
    Returns:
        True if complex (needs planning), False if simple
    """
    from config import small_llm
    from langchain_core.messages import SystemMessage, HumanMessage
    
    # Build context from conversation history if available
    context_str = ""
    if conversation_history and len(conversation_history) > 0:
        recent = conversation_history[-3:]  # Last 3 turns
        context_parts = []
        for turn in recent:
            context_parts.append(f"User: {turn.get('user_message', '')}")
            context_parts.append(f"Assistant: {turn.get('agent_response', '')}")
        context_str = "\n".join(context_parts)
    
    system_prompt = """You are a query complexity analyzer for a university assistant system.

Your ONLY job is to classify if a query requires PLANNING MODE (multi-step execution) or can be handled DIRECTLY.

**SIMPLE queries** (respond "SIMPLE"):
- Single factual questions: "Who is the rector?", "What is AI?"
- Direct lookups: "Show me BS CS program", "Tell me about faculty X"
- Greetings/small talk: "Hello", "Thanks", "Bye"
- Simple follow-ups with clear context: "What about his email?", "Tell me more"
- Exam generation requests (even custom ones): "Generate exam for CN, 50 marks, 180 min"
- Single-step modifications: "Make it harder", "Add more questions"

**COMPLEX queries** (respond "COMPLEX"):
- User-specific personalized requests needing clarification: "I'm in 6th semester, show me MY schedule" (needs to know which courses user selected)
- Multi-step aggregation: "Compare all CS programs AND tell me admission requirements AND recommend one"
- Conditional logic: "If I want to be an AI engineer, what should I study?"
- Questions requiring unknown user preferences: "Give me my complete timetable" (without knowing sections/electives)
- Multiple independent questions in one: "What are the requirements? And when do admissions open? And which program is best?"

**Key Rule**: If the assistant needs to ASK THE USER for clarification (electives chosen, preferences, etc.), classify as COMPLEX. If the assistant can answer with available data, classify as SIMPLE.

**Context-Aware**: Use conversation history to understand follow-ups. If context makes a query answerable, classify as SIMPLE.

Examples:
Q: "Who is the rector?"
A: SIMPLE

Q: "Generate exam for Computer Networks, 50 marks, 180 minutes with long questions"
A: SIMPLE

Q: "I'm a 6th semester BS AI student, give me my complete schedule"
A: COMPLEX (needs to know which electives user selected)

Q: "Compare BS CS vs BS AI and recommend which is better for machine learning"
A: SIMPLE (can answer with available data)

Q: "If I like math and programming, which degree should I choose and what courses are important?"
A: COMPLEX (multi-step with conditional logic)

Respond with ONLY "SIMPLE" or "COMPLEX". No explanation."""

    # Prepare the query with context
    user_message = f"Classify this query:\n\n"
    if context_str:
        user_message += f"Recent conversation:\n{context_str}\n\n"
    user_message += f"Current question: {question}"
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message)
    ]
    
    try:
        # Use small_llm for fast classification
        response = small_llm.invoke(messages)
        decision = response.content.strip().upper()
        
        # Validate response
        if "COMPLEX" in decision:
            return True
        elif "SIMPLE" in decision:
            return False
        else:
            # Fallback: use heuristic if LLM gives unexpected response
            return _heuristic_complexity_check(question)
            
    except Exception as e:
        # Fallback to heuristic on error
        print(f"[WARNING] small_llm complexity detection failed: {e}, using heuristic fallback")
        return _heuristic_complexity_check(question)


def _heuristic_complexity_check(question: str) -> bool:
    """Fallback heuristic-based complexity detection."""
    import re
    q_lower = question.lower().strip()
    
    # Definite simple patterns
    simple_patterns = [
        any(re.search(r'\b' + word + r'\b', q_lower) for word in ["hello", "hi", "hey", "thanks", "bye"]),
        q_lower.startswith("who is") and len(q_lower.split()) < 8,
        q_lower.startswith("what is") and len(q_lower.split()) < 8,
        q_lower.startswith("when is") and len(q_lower.split()) < 8,
        len(q_lower.split()) < 5 and "?" in q_lower,
    ]
    
    if any(simple_patterns):
        return False
    
    # Definite complex patterns
    complex_indicators = [
        "i'm a" in q_lower or "i am a" in q_lower,
        "my" in q_lower and ("schedule" in q_lower or "courses" in q_lower or "timetable" in q_lower),
        "if" in q_lower and "then" in q_lower,
        "first" in q_lower and ("then" in q_lower or "after" in q_lower),
        "complete" in q_lower and ("schedule" in q_lower or "timetable" in q_lower),
        q_lower.count("?") > 1 and " and " in q_lower,
        len(q_lower.split()) > 20,
    ]
    
    if any(complex_indicators):
        return True
    
    return False


if __name__ == "__main__":
    # Test complexity detection with small_llm
    test_cases = [
        ("Hello!", False, "Greeting"),
        ("Who is the rector?", False, "Single fact lookup"),
        ("What is AI?", False, "Definition question"),
        ("Tell me about BS CS", False, "Program info"),
        ("Generate exam for Computer Networks, 50 marks, 180 minutes", False, "Exam generation (direct)"),
        ("Make it harder", False, "Simple modification with context"),
        ("I'm a 6th semester BS AI student, give me my complete schedule", True, "Needs user-specific electives"),
        ("Compare BS CS and BS AI programs", False, "Comparison with available data"),
        ("What courses should I take and when are the exams?", False, "Two related questions"),
        ("Recommend me a degree program based on my interests in ML and data science", True, "Needs preference gathering"),
        ("If I want to become an AI engineer, what program should I choose and what courses are important?", True, "Conditional multi-step"),
    ]
    
    print("Complexity Detection Tests (using small_llm):")
    print("="*90)
    
    for query, expected, reason in test_cases:
        result = detect_query_complexity(query)
        status = "✅" if result == expected else "❌"
        expected_str = 'COMPLEX' if expected else 'SIMPLE'
        actual_str = 'COMPLEX' if result else 'SIMPLE'
        print(f"{status} [{expected_str:7}] {query[:50]:50} ({reason})")
        if result != expected:
            print(f"   ^ Got: {actual_str}")
    
    print("\n" + "="*90)
    print("Note: Using small_llm for intelligent classification with context awareness")
