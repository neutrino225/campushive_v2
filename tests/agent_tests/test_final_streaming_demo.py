"""
Final demonstration: Token-level streaming with complete exam generation.
This shows that the two-phase approach successfully provides progressive streaming.
"""

import sys
import time
import asyncio
from pathlib import Path

# Add root to path
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from multiagent.agents.exam_react_agent import ExamReactAgent


async def test_complete_exam_with_streaming():
    """Test complete exam generation with token-level streaming."""
    print("=" * 80)
    print("FINAL TEST: Complete Exam Generation with Token-Level Streaming")
    print("=" * 80)
    print()
    
    # Initialize the agent
    agent = ExamReactAgent()
    
    # Request a simple final exam (easier to generate completely)
    question = """Generate a final exam for Database Systems with 5 questions (50 marks total).
Question distribution:
- 3 short questions (20 marks)
- 2 long questions (30 marks)

Topics: SQL, Normalization, Transactions, Indexing.
Difficulty: Medium"""
    
    session_id = "final_demo"
    
    print(f"Request: {question}")
    print("\n" + "=" * 80)
    print("Phase 1: Agent running (tool calls + validation) - Please wait...")
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
            print("\n" + "=" * 80)
            print(f"✅ Phase 1 Complete! ({time_to_first_token:.2f}s)")
            print("=" * 80)
            print("Phase 2: Streaming final exam token-by-token...")
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
    print("RESULTS")
    print("=" * 80)
    print(f"✅ Streaming completed successfully!")
    print()
    print(f"📊 Metrics:")
    print(f"   • Total tokens streamed: {token_count}")
    print(f"   • Total characters: {char_count}")
    print(f"   • Total time: {total_time:.2f}s")
    
    if first_token_time:
        time_to_first_token = first_token_time - start_time
        streaming_time = end_time - first_token_time
        
        print()
        print(f"⏱️  Timing Breakdown:")
        print(f"   • Phase 1 (validation): {time_to_first_token:.2f}s")
        print(f"   • Phase 2 (streaming): {streaming_time:.2f}s")
        
        if streaming_time > 0:
            tokens_per_sec = token_count / streaming_time
            chars_per_sec = char_count / streaming_time
            print()
            print(f"🚀 Streaming Performance:")
            print(f"   • {tokens_per_sec:.1f} tokens/sec")
            print(f"   • {chars_per_sec:.1f} chars/sec")
    
    print()
    print("=" * 80)
    
    # Final verdict
    if token_count > 50:
        print("🎉 SUCCESS! Token-level streaming is WORKING!")
        print()
        print("✅ What this means:")
        print(f"   • Users see {token_count} progressive updates (not 1-2 big chunks)")
        print("   • Exam appears word-by-word in the UI")
        print("   • Much better UX than waiting for complete exam")
        print()
        print("✅ How it works:")
        print("   • Phase 1: Agent runs tools + validation (silent)")
        print("   • Phase 2: LLM streams final exam token-by-token")
        print("   • Result: Quality + Progressive feedback")
    else:
        print(f"⚠️  Only {token_count} tokens - may need investigation")
    
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_complete_exam_with_streaming())
