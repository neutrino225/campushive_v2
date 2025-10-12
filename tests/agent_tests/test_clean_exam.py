#!/usr/bin/env python3
"""Quick test to verify exam formatting fixes."""

import sys
import asyncio
from pathlib import Path

root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from multiagent.agents.exam_react_agent import ExamReactAgent


async def test_clean_exam_generation():
    """Test that exam generation is clean (no tool outputs, no answer blanks)."""
    
    agent = ExamReactAgent()
    session_id = "test_clean_session"
    
    print("=" * 80)
    print("TESTING CLEAN EXAM GENERATION")
    print("=" * 80)
    print()
    
    question = "Generate a final exam for Computer Networks with 5 questions, worth 50 marks"
    print(f"Request: {question}\n")
    print("Response:")
    print("-" * 80)
    
    response = ""
    async for chunk in agent.stream_async(question, session_id, "faculty"):
        print(chunk, end="", flush=True)
        response += chunk
    
    print("\n")
    print("=" * 80)
    print("VALIDATION CHECKS")
    print("=" * 80)
    
    # Check for issues
    issues = []
    
    if "Inspiration Question" in response:
        issues.append("❌ Contains tool output ('Inspiration Question')")
    else:
        print("✓ No tool output visible")
    
    if "Answer: ____" in response or "Answer:____" in response:
        issues.append("❌ Contains answer blanks")
    else:
        print("✓ No answer blanks")
    
    if "--- Inspiration" in response:
        issues.append("❌ Contains inspiration markers")
    else:
        print("✓ No inspiration markers")
    
    # Check structure
    if "Section A" in response or "Section B" in response:
        print("✓ Has proper section structure")
    else:
        issues.append("⚠️  Missing section structure")
    
    if "marks" in response.lower():
        print("✓ Includes marks allocation")
    else:
        issues.append("⚠️  Missing marks allocation")
    
    print()
    if issues:
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("🎉 ALL CHECKS PASSED!")
    
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_clean_exam_generation())
