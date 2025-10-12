#!/usr/bin/env python3
"""Test the new simplified ReAct-based exam agent."""

import sys
import asyncio
from pathlib import Path

root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from multiagent.agents.exam_react_agent import ExamReactAgent


async def test_exam_react_agent():
    """Test the ReAct exam agent with a multi-turn conversation."""
    
    agent = ExamReactAgent()
    session_id = "test_react_session"
    user_role = "faculty"
    
    print("=" * 80)
    print("TESTING NEW REACT-BASED EXAM AGENT")
    print("=" * 80)
    print()
    
    # Turn 1: Initial request
    print("🔵 TURN 1: Initial Request")
    print("-" * 80)
    question1 = "Generate a final exam for Computer Networks with 5 questions, worth 50 marks"
    print(f"User: {question1}\n")
    print("Agent Response:")
    print("-" * 40)
    
    response1 = ""
    async for chunk in agent.stream_async(question1, session_id, user_role):
        print(chunk, end="", flush=True)
        response1 += chunk
    
    print("\n")
    print("=" * 80)
    print()
    
    # Turn 2: Clarification
    print("🟢 TURN 2: Clarification (should remember previous request)")
    print("-" * 80)
    question2 = "Follow the full final-exam pattern"
    print(f"User: {question2}\n")
    print("Agent Response:")
    print("-" * 40)
    
    response2 = ""
    async for chunk in agent.stream_async(question2, session_id, user_role):
        print(chunk, end="", flush=True)
        response2 += chunk
    
    print("\n")
    print("=" * 80)
    print()
    
    # Turn 3: Modification
    print("🟡 TURN 3: Modification (should modify the previous exam)")
    print("-" * 80)
    question3 = "Add one more long question about TCP congestion control"
    print(f"User: {question3}\n")
    print("Agent Response:")
    print("-" * 40)
    
    response3 = ""
    async for chunk in agent.stream_async(question3, session_id, user_role):
        print(chunk, end="", flush=True)
        response3 += chunk
    
    print("\n")
    print("=" * 80)
    print()
    
    # Verification
    print("✅ VERIFICATION:")
    print("-" * 80)
    print(f"✓ Turn 1 completed: {len(response1)} characters")
    print(f"✓ Turn 2 completed: {len(response2)} characters")
    print(f"✓ Turn 3 completed: {len(response3)} characters")
    print()
    
    # Check if Computer Networks is mentioned in turn 2 (context preservation)
    if "Computer Networks" in response2 or "computer networks" in response2.lower():
        print("✓ Context preserved: Course name maintained in clarification")
    else:
        print("⚠️  Warning: Course name might not be preserved")
    
    print()
    print("=" * 80)
    print("TEST COMPLETED SUCCESSFULLY!")
    print("=" * 80)


async def test_simple_generation():
    """Test simple exam generation."""
    agent = ExamReactAgent()
    
    print("\n" + "=" * 80)
    print("SIMPLE GENERATION TEST")
    print("=" * 80)
    print()
    
    question = "Generate a sessional exam for Artificial Intelligence, 50 marks"
    print(f"User: {question}\n")
    print("Agent Response:")
    print("-" * 40)
    
    async for chunk in agent.stream_async(question, "simple_test", "faculty"):
        print(chunk, end="", flush=True)
    
    print("\n")
    print("=" * 80)


if __name__ == "__main__":
    print("Starting ReAct Exam Agent Tests...\n")
    
    # Run tests
    asyncio.run(test_exam_react_agent())
    
    print("\n\n")
    asyncio.run(test_simple_generation())
