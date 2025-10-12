"""
Test token-level streaming with a proper sessional exam request.
"""

import sys
import time
import asyncio
from pathlib import Path

# Add root to path
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from multiagent.agents.exam_react_agent import ExamReactAgent


async def test_sessional_exam_streaming():
    """Test token streaming with a proper sessional exam."""
    print("=" * 80)
    print("Testing Sessional Exam Generation with Token-Level Streaming")
    print("=" * 80)
    print()
    
    # Initialize the agent
    agent = ExamReactAgent()
    
    # Request a sessional exam following standard format
    question = """Generate a sessional exam for Operating Systems, 50 marks total.
Include: 20 MCQs (10 marks), 10 short questions (30 marks), 1 application problem (10 marks).
Topics: Process Scheduling, Memory Management, File Systems, Deadlocks.
Difficulty: Medium"""
    
    session_id = "sessional_test"
    
    print(f"Request: {question}")
    print()
    print("Streaming response:")
    print("=" * 80)
    
    # Track streaming metrics
    char_count = 0
    token_count = 0
    first_token_time = None
    start_time = time.time()
    
    # Stream the response
    async for token in agent.stream_async(question, session_id, user_role="faculty"):
        if first_token_time is None:
            first_token_time = time.time()
            time_to_first_token = first_token_time - start_time
            print(f"\n⏱️  Agent completed validation. Starting streaming after {time_to_first_token:.2f}s")
            print("=" * 80)
            print()
        
        print(token, end="", flush=True)
        token_count += 1
        char_count += len(token)
    
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
            print(f"   Streaming rate: {token_count / streaming_time:.1f} tokens/sec")
            print(f"   Character rate: {char_count / streaming_time:.1f} chars/sec")
    
    # Verify token-level streaming
    if token_count > 100:
        print(f"\n🎉 SUCCESS! Token-level streaming is working perfectly!")
        print(f"   Got {token_count} individual tokens streaming progressively")
        print(f"   Users will see the exam appear word-by-word instead of all at once")
    else:
        print(f"\n⚠️  Got {token_count} tokens (may need more for longer content)")


if __name__ == "__main__":
    asyncio.run(test_sessional_exam_streaming())
