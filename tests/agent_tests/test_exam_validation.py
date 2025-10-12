"""
Test script to verify exam agent validation and all requirements.
"""
import asyncio
import sys
from pathlib import Path

root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from multiagent.agents.exam_react_agent import ExamReactAgent


async def test_faculty_exam_generation():
    """Test faculty mode exam generation with validation."""
    print("=" * 80)
    print("TEST 1: FACULTY MODE - FINAL EXAM GENERATION")
    print("=" * 80)
    
    agent = ExamReactAgent()
    
    request = "Generate a final exam for Computer Networks with 100 marks"
    print(f"\nRequest: {request}")
    print(f"Role: faculty")
    print("\nGenerating exam...\n")
    print("-" * 80)
    
    full_response = ""
    async for chunk in agent.stream_async(request, session_id="test_faculty", user_role="faculty"):
        print(chunk, end="", flush=True)
        full_response += chunk
    
    print("\n" + "-" * 80)
    
    # Verify requirements
    print("\n" + "=" * 80)
    print("REQUIREMENT VERIFICATION")
    print("=" * 80)
    
    checks = {
        "Has Section A (MCQs)": "Section A" in full_response,
        "Has Section B": "Section B" in full_response,
        "Has Section C": "Section C" in full_response,
        "Has Answer Key": "ANSWER KEY" in full_response.upper() or "Answer Key" in full_response,
        "No tool output visible": "Inspiration Question" not in full_response,
        "No answer blanks": "Answer: _______" not in full_response and "_____" not in full_response,
        "Has marks allocation": "[" in full_response and "marks" in full_response.lower(),
        "MCQ format (A/B/C/D)": bool(
            "A." in full_response and 
            "B." in full_response and 
            "C." in full_response and 
            "D." in full_response
        ),
    }
    
    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check_name}")
    
    all_passed = all(checks.values())
    
    if all_passed:
        print("\n🎉 ALL REQUIREMENTS MET!")
    else:
        print("\n⚠️ SOME REQUIREMENTS NOT MET")
        failed = [name for name, passed in checks.items() if not passed]
        print(f"Failed checks: {', '.join(failed)}")
    
    return all_passed


async def test_student_exam_generation():
    """Test student mode exam generation."""
    print("\n\n" + "=" * 80)
    print("TEST 2: STUDENT MODE - PRACTICE EXAM GENERATION")
    print("=" * 80)
    
    agent = ExamReactAgent()
    
    request = "Generate a practice final exam for Artificial Intelligence with 100 marks"
    print(f"\nRequest: {request}")
    print(f"Role: student")
    print("\nGenerating practice exam...\n")
    print("-" * 80)
    
    full_response = ""
    async for chunk in agent.stream_async(request, session_id="test_student", user_role="student"):
        print(chunk, end="", flush=True)
        full_response += chunk
    
    print("\n" + "-" * 80)
    
    # Verify requirements
    print("\n" + "=" * 80)
    print("REQUIREMENT VERIFICATION")
    print("=" * 80)
    
    checks = {
        "Has Section A (MCQs)": "Section A" in full_response,
        "Has Section B": "Section B" in full_response,
        "No tool output visible": "Inspiration Question" not in full_response,
        "No answer blanks": "Answer: _______" not in full_response and "_____" not in full_response,
        "Has marks allocation": "[" in full_response and "marks" in full_response.lower(),
    }
    
    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check_name}")
    
    all_passed = all(checks.values())
    
    if all_passed:
        print("\n🎉 ALL REQUIREMENTS MET!")
    else:
        print("\n⚠️ SOME REQUIREMENTS NOT MET")
    
    return all_passed


async def test_sessional_exam():
    """Test sessional exam (50 marks)."""
    print("\n\n" + "=" * 80)
    print("TEST 3: SESSIONAL EXAM (50 MARKS)")
    print("=" * 80)
    
    agent = ExamReactAgent()
    
    request = "Generate a sessional exam for Data Structures with 50 marks"
    print(f"\nRequest: {request}")
    print(f"Role: faculty")
    print("\nGenerating exam...\n")
    print("-" * 80)
    
    full_response = ""
    async for chunk in agent.stream_async(request, session_id="test_sessional", user_role="faculty"):
        print(chunk, end="", flush=True)
        full_response += chunk
    
    print("\n" + "-" * 80)
    
    # Verify requirements
    print("\n" + "=" * 80)
    print("REQUIREMENT VERIFICATION")
    print("=" * 80)
    
    checks = {
        "Has Section A (MCQs)": "Section A" in full_response,
        "Has Section B": "Section B" in full_response,
        "Has Answer Key (Faculty)": "ANSWER KEY" in full_response.upper() or "Answer Key" in full_response,
        "No tool output visible": "Inspiration Question" not in full_response,
        "No answer blanks": "Answer: _______" not in full_response,
    }
    
    for check_name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check_name}")
    
    all_passed = all(checks.values())
    
    if all_passed:
        print("\n🎉 ALL REQUIREMENTS MET!")
    else:
        print("\n⚠️ SOME REQUIREMENTS NOT MET")
    
    return all_passed


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("COMPREHENSIVE EXAM AGENT VALIDATION TEST")
    print("=" * 80)
    
    results = []
    
    # Test 1: Faculty final exam
    try:
        result1 = await test_faculty_exam_generation()
        results.append(("Faculty Final Exam", result1))
    except Exception as e:
        print(f"\n❌ Test 1 failed with error: {e}")
        results.append(("Faculty Final Exam", False))
    
    # Test 2: Student practice exam
    try:
        result2 = await test_student_exam_generation()
        results.append(("Student Practice Exam", result2))
    except Exception as e:
        print(f"\n❌ Test 2 failed with error: {e}")
        results.append(("Student Practice Exam", False))
    
    # Test 3: Sessional exam
    try:
        result3 = await test_sessional_exam()
        results.append(("Sessional Exam", result3))
    except Exception as e:
        print(f"\n❌ Test 3 failed with error: {e}")
        results.append(("Sessional Exam", False))
    
    # Summary
    print("\n\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED! Exam agent is working perfectly!")
    else:
        print("\n⚠️ Some tests failed. Review the output above.")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
