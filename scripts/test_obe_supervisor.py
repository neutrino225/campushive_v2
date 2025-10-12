import sys
import asyncio
from pathlib import Path

# Add the root directory to the Python path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from multiagent.graph.supervisor import run_supervisor_async


async def test_obe_with_supervisor():
    """Test that OBE requests work through the supervisor."""
    
    # Test case 1: Direct OBE mapping request with CLOs and PLOs
    test_question_1 = """
    Map these outcomes:
    
    CLOs:
    - CLO 1: Understand basic algorithms and data structures
    - CLO 2: Implement efficient sorting and searching algorithms
    - CLO 3: Analyze algorithm complexity
    
    PLOs:
    - PLO 1: Apply knowledge of computing fundamentals
    - PLO 2: Design and develop software solutions
    - PLO 3: Analyze and solve complex computing problems
    """
    
    print("=" * 80)
    print("Test 1: OBE Mapping via Supervisor (with CLOs and PLOs)")
    print("=" * 80)
    print(f"Question: {test_question_1.strip()}\n")
    
    result = await run_supervisor_async(test_question_1, session_id="obe_test_1")
    
    print("Result:")
    print(result.get("response", "No response"))
    print(f"\nRoute: {result.get('route', [])}")
    print("\n")
    
    # Test case 2: General OBE question
    test_question_2 = "Can you help me map CLOs to PLOs?"
    
    print("=" * 80)
    print("Test 2: General OBE Question via Supervisor")
    print("=" * 80)
    print(f"Question: {test_question_2}\n")
    
    result = await run_supervisor_async(test_question_2, session_id="obe_test_2")
    
    print("Result:")
    print(result.get("response", "No response"))
    print(f"\nRoute: {result.get('route', [])}")
    print("\n")
    
    # Test case 3: Faculty info question (should not route to OBE)
    test_question_3 = "Who is the head of the computer science department?"
    
    print("=" * 80)
    print("Test 3: Faculty Info Question (should not go to OBE)")
    print("=" * 80)
    print(f"Question: {test_question_3}\n")
    
    result = await run_supervisor_async(test_question_3, session_id="obe_test_3")
    
    print("Result:")
    print(result.get("response", "No response"))
    print(f"\nRoute: {result.get('route', [])}")
    print("\n")


if __name__ == "__main__":
    asyncio.run(test_obe_with_supervisor())
