import sys
from pathlib import Path

# Add the root directory to the Python path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from multiagent.nodes.faculty import faculty_router_node
import json


def test_obe_routing():
    """Test that OBE-related questions are routed to the OBE agent."""
    
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
    print("Test 1: OBE Mapping with CLOs and PLOs")
    print("=" * 80)
    print(f"Question: {test_question_1.strip()}\n")
    
    try:
        state = {"question": test_question_1}
        print(f"Initial state: {json.dumps(state, indent=2)}\n")
        result = faculty_router_node.invoke(state)
        print(f"Result type: {type(result)}")
        print(f"Result keys: {result.keys() if result else 'None'}\n")
        
        print("Result:")
        if result:
            print(result.get("result", "No result"))
        else:
            print("Graph returned None")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    print("\n")
    
    # Test case 2: General OBE question
    test_question_2 = "Can you help me map CLOs to PLOs?"
    
    print("=" * 80)
    print("Test 2: General OBE Question")
    print("=" * 80)
    print(f"Question: {test_question_2}\n")
    
    state = {"question": test_question_2}
    result = faculty_router_node.invoke(state)
    
    print("Result:")
    if result:
        print(result.get("result", "No result"))
    else:
        print("Graph returned None")
    print("\n")
    
    # Test case 3: Faculty info question (should not route to OBE)
    test_question_3 = "Who is the head of the computer science department?"
    
    print("=" * 80)
    print("Test 3: Faculty Info Question (should not go to OBE)")
    print("=" * 80)
    print(f"Question: {test_question_3}\n")
    
    state = {"question": test_question_3}
    result = faculty_router_node.invoke(state)
    
    print("Result:")
    if result:
        print(result.get("result", "No result"))
    else:
        print("Graph returned None")
    print("\n")


if __name__ == "__main__":
    test_obe_routing()
