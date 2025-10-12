"""
Test script to verify improved validation display and clean streaming.
"""
import asyncio
import sys
from pathlib import Path

root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from multiagent.agents.exam_react_agent import ExamReactAgent


async def test_clean_streaming():
    """Test that validation messages are hidden and only final exam is shown."""
    print("=" * 80)
    print("TEST: CLEAN STREAMING - NO VALIDATION MESSAGES VISIBLE")
    print("=" * 80)
    
    agent = ExamReactAgent()
    
    request = "Generate a final exam for Computer Networks with 100 marks"
    print(f"\nRequest: {request}")
    print(f"Role: faculty")
    print("\nExpected: Only the final exam should appear, no validation checks\n")
    print("-" * 80)
    
    full_response = ""
    chunk_count = 0
    
    async for chunk in agent.stream_async(request, session_id="test_clean", user_role="faculty"):
        print(chunk, end="", flush=True)
        full_response += chunk
        chunk_count += 1
    
    print("\n" + "-" * 80)
    
    # Verify clean output
    print("\n" + "=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    
    checks = {
        "No validation checks visible": "🔍 VALIDATION CHECKS:" not in full_response,
        "No inspiration output": "--- Inspiration Question" not in full_response,
        "No validation failed messages": "❌ VALIDATION FAILED" not in full_response,
        "No issues found messages": "❌ ISSUES FOUND:" not in full_response,
        "Has exam content": "Section A" in full_response,
        "Has answer key": "ANSWER KEY" in full_response.upper() or "Answer Key" in full_response,
        "Received chunks": chunk_count > 0,
    }
    
    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check_name}")
    
    all_passed = all(checks.values())
    
    if all_passed:
        print("\n🎉 SUCCESS - Clean streaming working perfectly!")
        print("User only sees the final exam, not validation attempts.")
    else:
        print("\n⚠️ ISSUES DETECTED - Some validation messages may be visible")
        failed = [name for name, passed in checks.items() if not passed]
        print(f"Failed: {', '.join(failed)}")
    
    return all_passed


async def test_multi_turn_conversation():
    """Test that follow-ups work with clean streaming."""
    print("\n\n" + "=" * 80)
    print("TEST: MULTI-TURN CONVERSATION")
    print("=" * 80)
    
    agent = ExamReactAgent()
    session_id = "test_multiturn"
    
    # Turn 1: Initial request
    print("\n[Turn 1] Generate final exam for Database Systems, 100 marks")
    print("-" * 80)
    response1 = ""
    async for chunk in agent.stream_async(
        "Generate a final exam for Database Systems with 100 marks",
        session_id=session_id,
        user_role="faculty"
    ):
        response1 += chunk
    
    if len(response1) > 500:
        print(response1[:500] + "... (truncated)")
    else:
        print(response1)
    
    # Turn 2: Modification request
    print("\n\n[Turn 2] Add 2 more short questions")
    print("-" * 80)
    response2 = ""
    async for chunk in agent.stream_async(
        "Add 2 more short questions",
        session_id=session_id,
        user_role="faculty"
    ):
        response2 += chunk
    
    if len(response2) > 500:
        print(response2[:500] + "... (truncated)")
    else:
        print(response2)
    
    # Verify
    print("\n" + "=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    
    checks = {
        "Turn 1: Clean output": "🔍 VALIDATION" not in response1 and "--- Inspiration" not in response1,
        "Turn 1: Has exam": "Section A" in response1,
        "Turn 2: Clean output": "🔍 VALIDATION" not in response2 and "--- Inspiration" not in response2,
        "Turn 2: Has content": len(response2) > 100,
    }
    
    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check_name}")
    
    all_passed = all(checks.values())
    
    if all_passed:
        print("\n🎉 Multi-turn conversation working with clean streaming!")
    else:
        print("\n⚠️ Some issues in multi-turn conversation")
    
    return all_passed


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("CLEAN STREAMING VALIDATION TEST SUITE")
    print("=" * 80)
    
    results = []
    
    try:
        result1 = await test_clean_streaming()
        results.append(("Clean Streaming", result1))
    except Exception as e:
        print(f"\n❌ Test 1 failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Clean Streaming", False))
    
    try:
        result2 = await test_multi_turn_conversation()
        results.append(("Multi-turn Conversation", result2))
    except Exception as e:
        print(f"\n❌ Test 2 failed with error: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Multi-turn Conversation", False))
    
    # Summary
    print("\n\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ Validation runs silently in background")
        print("✅ Users only see clean exam output")
        print("✅ No tool outputs or validation checks visible")
    else:
        print("\n⚠️ Some tests failed. Review output above.")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
