"""
Test OBE Agent document integration

Tests:
1. Extract CLOs/PLOs from uploaded documents
2. Improve outcomes using OBE best practices
3. Generate CLO-PLO mapping with auto-extraction
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_obe_extraction():
    """Test CLO/PLO extraction from documents"""
    from multiagent.agents.obe_agent.obe_agent import OBEAgent
    from multiagent.memory.retriever_manager import get_session_retriever_manager
    
    print("=" * 60)
    print("TEST 1: OBE Agent - Extract Outcomes from Document")
    print("=" * 60)
    
    # Create test course outline
    course_outline = """
    CS501 - Advanced Software Engineering
    Course Outline
    
    Course Learning Outcomes (CLOs):
    Upon completion of this course, students will be able to:
    
    CLO1: Analyze complex software systems and identify design patterns
    CLO2: Design and implement scalable software architectures
    CLO3: Apply agile methodologies in software development projects
    CLO4: Evaluate software quality using various testing techniques
    CLO5: Communicate technical decisions effectively to stakeholders
    
    Program Learning Outcomes (PLOs):
    This course contributes to the following program outcomes:
    
    PLO1: An ability to analyze problems and identify computing requirements
    PLO2: An ability to design, implement, and evaluate computing solutions
    PLO3: An ability to function effectively in teams
    PLO4: An ability to communicate effectively with various stakeholders
    PLO5: An ability to engage in lifelong learning and professional development
    
    Prerequisites: CS301, CS302
    Credits: 3
    """
    
    # Ingest the course outline
    print("\n1. Ingesting course outline...")
    manager = get_session_retriever_manager()
    user_id = 777
    session_id = "obe_test_session"
    
    try:
        result = manager.ingest_document(
            user_id=user_id,
            session_id=session_id,
            text_content=course_outline,
            filename="CS501_outline.txt"
        )
        print(f"   ✅ Ingested {result['chunks_created']} chunks")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Extract outcomes
    print("\n2. Extracting CLOs and PLOs...")
    agent = OBEAgent()
    
    try:
        extraction = agent.extract_outcomes_from_document(
            user_id=user_id,
            session_id=session_id,
            outcome_type="both"
        )
        
        if "error" in extraction:
            print(f"   ❌ {extraction['error']}")
        else:
            print(f"   ✅ Extracted {len(extraction['clos'])} CLOs")
            print(f"   ✅ Extracted {len(extraction['plos'])} PLOs")
            
            print("\n   CLOs Found:")
            for i, clo in enumerate(extraction['clos'], 1):
                print(f"   {i}. {clo[:80]}...")
            
            print("\n   PLOs Found:")
            for i, plo in enumerate(extraction['plos'], 1):
                print(f"   {i}. {plo[:80]}...")
    
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Cleanup
    print("\n3. Cleanup...")
    deleted = manager.delete_session_store(user_id, session_id)
    print(f"   {'✅' if deleted else '❌'} Cleaned up test data")
    
    print("\n✅ OBE extraction test complete\n")


def test_obe_improvement():
    """Test CLO/PLO improvement"""
    from multiagent.agents.obe_agent.obe_agent import OBEAgent
    
    print("=" * 60)
    print("TEST 2: OBE Agent - Improve Outcomes")
    print("=" * 60)
    
    # Sample CLOs that need improvement
    weak_clos = [
        "Students will learn Python programming",
        "Understand data structures",
        "Know about algorithms"
    ]
    
    print("\n1. Original CLOs (weak):")
    for i, clo in enumerate(weak_clos, 1):
        print(f"   {i}. {clo}")
    
    print("\n2. Requesting improvements...")
    agent = OBEAgent()
    
    try:
        improvement = agent.improve_outcomes(
            outcomes=weak_clos,
            outcome_type="CLO",
            improvement_focus="clarity, measurability, and Bloom's taxonomy alignment"
        )
        
        if "error" in improvement:
            print(f"   ❌ {improvement['error']}")
        else:
            print("   ✅ Improvements generated")
            print("\n" + "=" * 60)
            print("IMPROVED OUTCOMES:")
            print("=" * 60)
            print(improvement['improved_response'])
    
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ OBE improvement test complete\n")


def test_obe_auto_extraction():
    """Test automatic extraction in run method"""
    from multiagent.agents.obe_agent.obe_agent import OBEAgent
    from multiagent.memory.retriever_manager import get_session_retriever_manager
    
    print("=" * 60)
    print("TEST 3: OBE Agent - Auto-Extract and Map")
    print("=" * 60)
    
    # Create test course outline
    course_outline = """
    DS502 - Data Science Fundamentals
    
    Course Learning Outcomes:
    CLO1: Apply statistical methods to analyze real-world datasets
    CLO2: Design and implement machine learning models
    CLO3: Visualize and communicate data insights effectively
    
    Program Learning Outcomes:
    PLO1: Problem analysis and solution design
    PLO2: Modern tool usage
    PLO3: Communication skills
    PLO4: Ethical data handling
    """
    
    # Ingest
    print("\n1. Ingesting course outline...")
    manager = get_session_retriever_manager()
    user_id = 888
    session_id = "obe_auto_test"
    
    result = manager.ingest_document(
        user_id=user_id,
        session_id=session_id,
        text_content=course_outline,
        filename="DS502_outline.txt"
    )
    print(f"   ✅ Ingested {result['chunks_created']} chunks")
    
    # Auto-extract and map
    print("\n2. Running OBE agent with auto-extraction...")
    agent = OBEAgent()
    
    try:
        # Call with empty CLOs/PLOs - should auto-extract
        mapping = agent.run(
            clos=[],
            plos=[],
            user_id=user_id,
            session_id=session_id
        )
        
        print("   ✅ Mapping generated")
        print("\n" + "=" * 60)
        print("CLO-PLO MAPPING:")
        print("=" * 60)
        print(mapping)
    
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Cleanup
    print("\n3. Cleanup...")
    deleted = manager.delete_session_store(user_id, session_id)
    print(f"   {'✅' if deleted else '❌'} Cleaned up test data")
    
    print("\n✅ OBE auto-extraction test complete\n")


def main():
    """Run all OBE agent tests"""
    print("\n" + "=" * 60)
    print("OBE AGENT DOCUMENT INTEGRATION TESTS")
    print("=" * 60 + "\n")
    
    try:
        # Test 1: Extraction
        test_obe_extraction()
        
        # Test 2: Improvement
        test_obe_improvement()
        
        # Test 3: Auto-extraction
        test_obe_auto_extraction()
        
        print("=" * 60)
        print("ALL OBE AGENT TESTS COMPLETED ✅")
        print("=" * 60 + "\n")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user\n")
    except Exception as e:
        print(f"\n\n❌ Test suite failed with error: {e}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
