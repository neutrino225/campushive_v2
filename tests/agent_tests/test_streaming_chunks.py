"""
Test script to verify streaming yields incremental chunks, not full content at once.
"""
import asyncio
import sys
import time
from pathlib import Path

root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from multiagent.agents.exam_react_agent import ExamReactAgent


async def test_incremental_streaming():
    """Test that streaming yields incremental chunks."""
    print("=" * 80)
    print("TEST: INCREMENTAL STREAMING")
    print("=" * 80)
    
    agent = ExamReactAgent()
    
    request = "Generate a final exam for Computer Networks with 100 marks"
    print(f"\nRequest: {request}")
    print(f"Role: faculty")
    print("\nExpected: Content should stream incrementally, not all at once\n")
    print("-" * 80)
    
    chunk_count = 0
    chunk_sizes = []
    start_time = time.time()
    last_chunk_time = start_time
    
    async for chunk in agent.stream_async(request, session_id="test_streaming", user_role="faculty"):
        chunk_count += 1
        chunk_size = len(chunk)
        chunk_sizes.append(chunk_size)
        
        current_time = time.time()
        time_since_last = current_time - last_chunk_time
        last_chunk_time = current_time
        
        # Print first few characters of chunk to show it's streaming
        preview = chunk[:50].replace('\n', '\\n') if len(chunk) > 50 else chunk.replace('\n', '\\n')
        print(f"[Chunk {chunk_count}] {chunk_size} chars, {time_since_last:.3f}s: {preview}...")
        
        # In real UI, you'd print the chunk directly
        # print(chunk, end="", flush=True)
    
    total_time = time.time() - start_time
    
    print("\n" + "-" * 80)
    print(f"\nTotal chunks received: {chunk_count}")
    print(f"Total time: {total_time:.2f}s")
    print(f"Average chunk size: {sum(chunk_sizes) / len(chunk_sizes):.0f} chars")
    print(f"Total content: {sum(chunk_sizes)} chars")
    
    # Verify streaming behavior
    print("\n" + "=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    
    checks = {
        "Multiple chunks received": chunk_count > 1,
        "Chunks received over time": total_time > 0.5,  # Should take some time
        "Not single massive chunk": chunk_count > 5,  # At least a few chunks
        "Progressive delivery": max(chunk_sizes) < sum(chunk_sizes),  # Not all at once
    }
    
    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check_name}")
    
    all_passed = all(checks.values())
    
    if all_passed:
        print("\n🎉 SUCCESS - Streaming works incrementally!")
        print("Content is delivered in chunks, not all at once.")
    else:
        print("\n⚠️ STREAMING ISSUE DETECTED")
        if chunk_count <= 1:
            print("⚠️ Only received 1 chunk - content delivered all at once")
            print("This means the UI will wait for the full response before showing anything")
    
    return all_passed


async def test_quick_response():
    """Test a simpler request to see streaming behavior."""
    print("\n\n" + "=" * 80)
    print("TEST: QUICK RESPONSE STREAMING")
    print("=" * 80)
    
    agent = ExamReactAgent()
    
    request = "Generate a sessional exam for Database Systems with 50 marks"
    print(f"\nRequest: {request}")
    print("-" * 80)
    
    chunk_count = 0
    start_time = time.time()
    
    print("\nStreaming output (showing actual content):\n")
    async for chunk in agent.stream_async(request, session_id="test_quick", user_role="student"):
        print(chunk, end="", flush=True)
        chunk_count += 1
    
    total_time = time.time() - start_time
    
    print("\n\n" + "-" * 80)
    print(f"Chunks: {chunk_count}, Time: {total_time:.2f}s")
    
    if chunk_count > 1:
        print("✅ Streaming working - content delivered incrementally")
    else:
        print("❌ Content delivered in single chunk")
    
    return chunk_count > 1


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("STREAMING CHUNK VERIFICATION TEST")
    print("=" * 80)
    
    try:
        result1 = await test_incremental_streaming()
    except Exception as e:
        print(f"\n❌ Test 1 failed with error: {e}")
        import traceback
        traceback.print_exc()
        result1 = False
    
    try:
        result2 = await test_quick_response()
    except Exception as e:
        print(f"\n❌ Test 2 failed with error: {e}")
        import traceback
        traceback.print_exc()
        result2 = False
    
    print("\n\n" + "=" * 80)
    print("FINAL VERDICT")
    print("=" * 80)
    
    if result1 and result2:
        print("✅ Streaming is working correctly!")
        print("✅ Content is delivered incrementally")
        print("✅ UI should show progressive updates")
    else:
        print("⚠️ Streaming needs attention")
        if not result1:
            print("❌ Main test shows content delivered all at once")
        if not result2:
            print("❌ Quick test shows single chunk delivery")


if __name__ == "__main__":
    asyncio.run(main())
