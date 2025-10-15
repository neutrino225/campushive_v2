#!/usr/bin/env python3
"""
Comprehensive End-to-End Test for Document Upload and OBE Extraction

This script tests the complete workflow:
1. Upload document to session
2. Verify document is stored in vector store
3. Query retriever to ensure documents are retrievable
4. Test OBE agent extraction
5. Test OBE agent mapping with extracted outcomes
"""

import sys
import os
from pathlib import Path

# Add project root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

from config import embeddings
from multiagent.memory.retriever_manager import (
    get_session_retriever_manager,
    get_session_retriever,
    has_session_documents
)
from multiagent.agents.obe_agent.obe_agent import OBEAgent


def print_section(title: str):
    """Print a section header"""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80 + "\n")


def print_success(message: str):
    """Print success message"""
    print(f"✅ {message}")


def print_error(message: str):
    """Print error message"""
    print(f"❌ {message}")


def print_info(message: str):
    """Print info message"""
    print(f"ℹ️  {message}")


def test_1_document_upload():
    """Test 1: Upload a test document to a session"""
    print_section("Test 1: Document Upload to Session")
    
    # Test parameters
    user_id = 999
    session_id = "test_session_123"
    
    # Create test document content
    test_document = """
# Course Outline: Computer Vision (AI-4002)

## Course Learning Outcomes (CLOs)

Upon completion of this course, students will be able to:

1. **CLO-1**: Analyze fundamental concepts of computer vision including image formation, feature extraction, and pattern recognition techniques.

2. **CLO-2**: Design and implement computer vision algorithms for image preprocessing, edge detection, and object recognition using Python and OpenCV.

3. **CLO-3**: Evaluate different deep learning architectures (CNNs, R-CNNs, YOLO) for visual recognition tasks and select appropriate models for specific applications.

4. **CLO-4**: Create end-to-end computer vision systems that integrate multiple techniques for real-world applications such as facial recognition or autonomous navigation.

5. **CLO-5**: Apply optimization techniques to improve the performance and efficiency of computer vision models in resource-constrained environments.

## Program Learning Outcomes (PLOs)

This course contributes to the following program-level outcomes:

1. **PLO-1**: An ability to analyze complex computing problems and to apply principles of computing and other relevant disciplines to identify solutions.

2. **PLO-2**: An ability to design, implement, and evaluate a computing-based solution to meet a given set of computing requirements in the context of the program's discipline.

3. **PLO-3**: An ability to communicate effectively in a variety of professional contexts.

4. **PLO-4**: An ability to recognize professional responsibilities and make informed judgments in computing practice based on legal and ethical principles.

5. **PLO-5**: An ability to function effectively as a member or leader of a team engaged in activities appropriate to the program's discipline.

6. **PLO-6**: An ability to apply computer science theory and software development fundamentals to produce computing-based solutions.

## Course Topics

- Image Formation and Representation
- Filtering and Edge Detection
- Feature Detection and Matching
- Object Recognition and Classification
- Convolutional Neural Networks
- Deep Learning for Computer Vision
- Object Detection (R-CNN, YOLO, SSD)
- Image Segmentation
- 3D Vision and Geometry
- Video Analysis and Tracking

## Assessment Methods

- Assignments: 20%
- Quizzes: 10%
- Midterm Exam: 20%
- Final Project: 30%
- Final Exam: 20%
"""
    
    try:
        # Get the session retriever manager
        manager = get_session_retriever_manager(embeddings)
        print_info(f"Manager initialized: {manager}")
        
        # Ingest the document
        print_info(f"Uploading document for user_id={user_id}, session_id={session_id}")
        result = manager.ingest_document(
            user_id=user_id,
            session_id=session_id,
            text_content=test_document,
            filename="test_course_outline.txt"
        )
        
        print_success(f"Document uploaded successfully!")
        print_info(f"Chunks created: {result['chunks_created']}")
        print_info(f"Store path: {result['store_path']}")
        
        # Verify the store exists
        if os.path.exists(result['store_path']):
            print_success(f"Vector store directory exists: {result['store_path']}")
        else:
            print_error(f"Vector store directory NOT found: {result['store_path']}")
            return False
        
        return True
        
    except Exception as e:
        print_error(f"Upload failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_2_retriever_verification():
    """Test 2: Verify retriever can access uploaded documents"""
    print_section("Test 2: Retriever Verification")
    
    user_id = 999
    session_id = "test_session_123"
    
    try:
        # Check if documents exist
        has_docs = has_session_documents(user_id, session_id)
        if has_docs:
            print_success(f"Session has documents: {has_docs}")
        else:
            print_error(f"Session has NO documents!")
            return False
        
        # Get retriever
        print_info(f"Getting retriever for user_id={user_id}, session_id={session_id}")
        retriever = get_session_retriever(user_id, session_id, search_kwargs={"k": 5})
        
        if retriever is None:
            print_error("Retriever is None!")
            return False
        
        print_success("Retriever obtained successfully")
        
        # Test retrieval with different queries
        test_queries = [
            "course learning outcomes CLO",
            "program learning outcomes PLO",
            "computer vision CNN deep learning",
            "design implement algorithms"
        ]
        
        for query in test_queries:
            print_info(f"\nQuerying: '{query}'")
            docs = retriever.get_relevant_documents(query)
            
            if len(docs) > 0:
                print_success(f"Retrieved {len(docs)} documents")
                print_info(f"First result preview: {docs[0].page_content[:150]}...")
            else:
                print_error(f"No documents retrieved for query: {query}")
        
        return True
        
    except Exception as e:
        print_error(f"Retriever verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_3_obe_extraction():
    """Test 3: OBE agent extraction from uploaded document"""
    print_section("Test 3: OBE Agent Extraction")
    
    user_id = 999
    session_id = "test_session_123"
    
    try:
        # Initialize OBE agent
        print_info("Initializing OBE agent...")
        obe_agent = OBEAgent()
        print_success("OBE agent initialized")
        
        # Test extraction
        print_info(f"Extracting outcomes for user_id={user_id}, session_id={session_id}")
        extraction_result = obe_agent.extract_outcomes_from_document(
            user_id=user_id,
            session_id=session_id,
            outcome_type="both"
        )
        
        # Check for errors
        if "error" in extraction_result:
            print_error(f"Extraction error: {extraction_result['error']}")
            return False
        
        # Display extracted CLOs
        clos = extraction_result.get("clos", [])
        print_success(f"Extracted {len(clos)} CLOs:")
        for i, clo in enumerate(clos, 1):
            print(f"  CLO-{i}: {clo[:80]}...")
        
        # Display extracted PLOs
        plos = extraction_result.get("plos", [])
        print_success(f"Extracted {len(plos)} PLOs:")
        for i, plo in enumerate(plos, 1):
            print(f"  PLO-{i}: {plo[:80]}...")
        
        # Verify we got reasonable results
        if len(clos) == 0:
            print_error("No CLOs extracted!")
            print_info("Raw text retrieved:")
            print(extraction_result.get("raw_text", "No raw text")[:500])
            print_info("\nExtracted text from LLM:")
            print(extraction_result.get("extracted_text", "No extracted text")[:500])
            return False
        
        if len(plos) == 0:
            print_error("No PLOs extracted!")
            return False
        
        print_success("Extraction completed successfully!")
        
        # Store for next test
        return extraction_result
        
    except Exception as e:
        print_error(f"OBE extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_4_obe_mapping(extraction_result):
    """Test 4: Generate advanced CLO-PLO mapping"""
    print_section("Test 4: Advanced CLO-PLO Mapping")
    
    if not extraction_result or "error" in extraction_result:
        print_error("Cannot test mapping without extracted outcomes")
        return False
    
    try:
        # Initialize OBE agent
        obe_agent = OBEAgent()
        
        clos = extraction_result["clos"]
        plos = extraction_result["plos"]
        
        print_info(f"Generating mapping for {len(clos)} CLOs and {len(plos)} PLOs...")
        print_info("This may take a moment...")
        
        # Generate mapping
        mapping_result = obe_agent.generate_advanced_mapping(
            clos=clos,
            plos=plos,
            threshold=0.4,
            use_llm_refinement=True
        )
        
        print_success("Mapping generated successfully!")
        print("\n" + "-" * 80)
        print(mapping_result)
        print("-" * 80)
        
        return True
        
    except Exception as e:
        print_error(f"Mapping generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_5_end_to_end():
    """Test 5: Complete end-to-end workflow"""
    print_section("Test 5: End-to-End Workflow (run() method)")
    
    user_id = 999
    session_id = "test_session_123"
    
    try:
        # Initialize OBE agent
        obe_agent = OBEAgent()
        
        # Call run() with empty CLOs/PLOs to trigger extraction
        print_info("Calling obe_agent.run() with empty CLOs/PLOs...")
        print_info("This should trigger automatic extraction from uploaded document")
        
        result = obe_agent.run(
            clos=[],  # Empty - should extract from document
            plos=[],  # Empty - should extract from document
            user_id=user_id,
            session_id=session_id
        )
        
        if "❌" in result:
            print_error("Run method returned error:")
            print(result)
            return False
        
        print_success("End-to-end run completed successfully!")
        print("\n" + "-" * 80)
        print(result[:1000])  # Print first 1000 chars
        print("...")
        print("-" * 80)
        
        return True
        
    except Exception as e:
        print_error(f"End-to-end test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def cleanup():
    """Clean up test data"""
    print_section("Cleanup")
    
    user_id = 999
    session_id = "test_session_123"
    
    try:
        manager = get_session_retriever_manager()
        success = manager.delete_session_store(user_id, session_id)
        
        if success:
            print_success("Test vector store deleted")
        else:
            print_info("No test vector store to delete")
        
    except Exception as e:
        print_error(f"Cleanup failed: {e}")


def main():
    """Run all tests"""
    print("\n" + "█" * 80)
    print("  End-to-End Document Upload and OBE Extraction Test Suite")
    print("  Testing: Upload → Store → Retrieve → Extract → Map")
    print("█" * 80)
    
    # Track test results
    results = {
        "Test 1: Document Upload": False,
        "Test 2: Retriever Verification": False,
        "Test 3: OBE Extraction": False,
        "Test 4: Advanced Mapping": False,
        "Test 5: End-to-End": False
    }
    
    # Run tests in sequence
    if test_1_document_upload():
        results["Test 1: Document Upload"] = True
        
        if test_2_retriever_verification():
            results["Test 2: Retriever Verification"] = True
            
            extraction_result = test_3_obe_extraction()
            if extraction_result:
                results["Test 3: OBE Extraction"] = True
                
                if test_4_obe_mapping(extraction_result):
                    results["Test 4: Advanced Mapping"] = True
            
            if test_5_end_to_end():
                results["Test 5: End-to-End"] = True
    
    # Print summary
    print_section("Test Summary")
    
    all_passed = True
    for test_name, passed in results.items():
        if passed:
            print_success(f"{test_name}")
        else:
            print_error(f"{test_name}")
            all_passed = False
    
    print("\n" + "=" * 80)
    
    if all_passed:
        print("🎉 All tests PASSED! System is working correctly.")
        print("\nThe document upload and OBE extraction system is fully functional:")
        print("  ✓ Documents are uploaded and chunked correctly")
        print("  ✓ Vector store retriever works properly")
        print("  ✓ OBE agent can extract CLOs/PLOs from documents")
        print("  ✓ Advanced mapping generates with composite scores")
        print("  ✓ End-to-end workflow functions as expected")
    else:
        print("⚠️  Some tests FAILED. Please review the errors above.")
        print("\nFailed tests indicate issues that need to be addressed.")
    
    print("=" * 80 + "\n")
    
    # Cleanup
    cleanup()
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
