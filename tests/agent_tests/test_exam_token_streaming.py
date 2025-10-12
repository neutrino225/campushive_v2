"""
Test token-level streaming for the Exam React Agent.

This script verifies that the exam agent now streams token-by-token
using the two-phase approach (complete agent execution, then stream final output).
"""

import sys
import time
import asyncio
from pathlib import Path

# Add root to path
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from multiagent.agents.exam_react_agent import ExamReactAgent


async def test_token_streaming():
    """Test that exam agent streams tokens progressively."""
    print("=" * 80)
    print("Testing Exam Agent Token-Level Streaming")
    print("=" * 80)
    print()
    
    # Initialize the agent
    agent = ExamReactAgent()
    
    # Create a simple exam request
    question = "Generate a quiz for Operating Systems with 3 questions worth 30 marks total"
    session_id = "token_stream_test"
    
    print(f"Request: {question}")
    print()
    print("Streaming response (each '.' is a token):")
    print("-" * 80)
    
    # Track streaming metrics
    token_count = 0
    first_token_time = None
    start_time = time.time()
    
    # Stream the response
    async for token in agent.stream_async(question, session_id, user_role="faculty"):
        if first_token_time is None:
            first_token_time = time.time()
            time_to_first_token = first_token_time - start_time
            print(f"\n⏱️  Time to first token: {time_to_first_token:.2f}s\n")
        
        print(token, end="", flush=True)
        token_count += 1
    
    end_time = time.time()
    total_time = end_time - start_time
    
    print()
    print("-" * 80)
    print(f"\n✅ Streaming completed!")
    print(f"   Total tokens: {token_count}")
    print(f"   Total time: {total_time:.2f}s")
    if first_token_time:
        print(f"   Time to first token: {time_to_first_token:.2f}s")
        print(f"   Streaming time: {end_time - first_token_time:.2f}s")
    
    # Verify token-level streaming (should have many tokens, not just 1-2)
    if token_count > 10:
        print(f"\n🎉 SUCCESS! Token-level streaming is working ({token_count} tokens)")
    else:
        print(f"\n⚠️  WARNING: Only {token_count} tokens received. May still be chunked.")


if __name__ == "__main__":
    asyncio.run(test_token_streaming())
