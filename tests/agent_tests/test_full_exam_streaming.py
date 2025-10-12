"""
Test token-level streaming with a complete exam generation request.
"""

import sys
import time
import asyncio
from pathlib import Path

# Add root to path
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from multiagent.agents.exam_react_agent import ExamReactAgent


async def test_full_exam_streaming():
    """Test token streaming with a complete exam generation."""
    print("=" * 80)
    print("Testing Full Exam Generation with Token-Level Streaming")
    print("=" * 80)
    print()
    
    # Initialize the agent
    agent = ExamReactAgent()
    
    # Request a complete exam (sessional format with 5 questions, 50 marks)
    question = """Generate a sessional exam for Computer Networks with exactly 5 questions, total 50 marks.
Topics: TCP/IP, OSI Model, Network Security, Routing Protocols.
Difficulty: Medium"""
    
    session_id = "full_exam_test"
    
    print(f"Request: {question}")
    print()
    print("Streaming response:")
    print("=" * 80)
    
    # Track streaming metrics
    char_count = 0
    token_count = 0
    first_token_time = None
    start_time = time.time()
    last_print_time = start_time
    
    # Stream the response
    async for token in agent.stream_async(question, session_id, user_role="faculty"):
        if first_token_time is None:
            first_token_time = time.time()
            time_to_first_token = first_token_time - start_time
            print(f"\n⏱️  Time to first token: {time_to_first_token:.2f}s")
            print("=" * 80)
            print()
        
        print(token, end="", flush=True)
        token_count += 1
        char_count += len(token)
        
        # Print progress every 2 seconds
        current_time = time.time()
        if current_time - last_print_time >= 2.0:
            elapsed = current_time - start_time
            print(f"\n[Progress: {token_count} tokens, {char_count} chars, {elapsed:.1f}s elapsed]\n", end="", flush=True)
            last_print_time = current_time
    
    end_time = time.time()
    total_time = end_time - start_time
    
    print()
    print()
    print("=" * 80)
    print(f"✅ Streaming completed!")
    print(f"   Total tokens: {token_count}")
    print(f"   Total characters: {char_count}")
    print(f"   Total time: {total_time:.2f}s")
    if first_token_time:
        print(f"   Time to first token: {time_to_first_token:.2f}s")
        streaming_time = end_time - first_token_time
        print(f"   Streaming time: {streaming_time:.2f}s")
        if streaming_time > 0:
            print(f"   Streaming rate: {char_count / streaming_time:.1f} chars/sec")
    
    # Verify token-level streaming
    if token_count > 50:
        print(f"\n🎉 SUCCESS! Token-level streaming is working perfectly!")
        print(f"   Got {token_count} tokens instead of 1-2 large chunks")
    else:
        print(f"\n⚠️  WARNING: Only {token_count} tokens received")


if __name__ == "__main__":
    asyncio.run(test_full_exam_streaming())
