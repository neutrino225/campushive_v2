"""
Quick test script for file upload functionality

Tests:
1. Document parser with sample text
2. Session retriever manager
3. End-to-end ingestion workflow
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_document_parser():
    """Test document parser with sample content"""
    from multiagent.utils.document_parser import (
        parse_document, is_supported_file, get_supported_extensions
    )
    
    print("=" * 60)
    print("TEST 1: Document Parser")
    print("=" * 60)
    
    # Test supported extensions
    print("\n1. Supported extensions:")
    print(get_supported_extensions())
    
    # Test file validation
    print("\n2. File validation:")
    test_files = ["test.txt", "test.pdf", "test.exe", "test.docx"]
    for filename in test_files:
        result = "✅" if is_supported_file(filename) else "❌"
        print(f"   {result} {filename}")
    
    # Test parsing plain text
    print("\n3. Parse plain text:")
    sample_text = b"This is a test document.\nIt has multiple lines.\nFor testing purposes."
    try:
        parsed = parse_document(sample_text, "test.txt")
        print(f"   ✅ Parsed: {len(parsed)} characters")
        print(f"   Preview: {parsed[:50]}...")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test parsing markdown
    print("\n4. Parse markdown:")
    markdown_text = b"# Test Document\n\n## Section 1\n\nSome content here."
    try:
        parsed = parse_document(markdown_text, "test.md")
        print(f"   ✅ Parsed: {len(parsed)} characters")
        print(f"   Preview: {parsed[:50]}...")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n✅ Document parser tests complete\n")


def test_session_retriever():
    """Test session retriever manager"""
    from multiagent.memory.retriever_manager import (
        SessionRetrieverManager, get_session_retriever_manager,
        get_session_retriever, has_session_documents
    )
    from config import embeddings
    
    print("=" * 60)
    print("TEST 2: Session Retriever Manager")
    print("=" * 60)
    
    # Initialize manager
    print("\n1. Initialize manager:")
    manager = SessionRetrieverManager(embeddings)
    print(f"   ✅ Manager created with base path: {manager.base_path}")
    
    # Test path generation
    print("\n2. Test path generation:")
    test_user_id = 999
    test_session_id = "test_session_123"
    path = manager.get_session_store_path(test_user_id, test_session_id)
    print(f"   Path: {path}")
    
    # Test document ingestion
    print("\n3. Test document ingestion:")
    sample_text = """
    Introduction to Computer Science
    
    Computer science is the study of computation, information, and automation.
    It includes both theoretical and practical aspects.
    
    Key Topics:
    - Algorithms and Data Structures
    - Programming Languages
    - Computer Architecture
    - Operating Systems
    - Databases
    
    This is a fundamental course for all CS students.
    """
    
    try:
        result = manager.ingest_document(
            user_id=test_user_id,
            session_id=test_session_id,
            text_content=sample_text,
            filename="intro_cs.txt"
        )
        print(f"   ✅ Ingestion successful:")
        print(f"      - Filename: {result['filename']}")
        print(f"      - Chunks: {result['chunks_created']}")
        print(f"      - Store path: {result['store_path']}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Test retriever creation
    print("\n4. Test retriever creation:")
    try:
        retriever = manager.get_session_retriever(test_user_id, test_session_id)
        if retriever:
            print(f"   ✅ Retriever created successfully")
            print(f"      Type: {type(retriever)}")
        else:
            print(f"   ❌ Retriever is None")
            return
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Test has_documents
    print("\n5. Test has_documents check:")
    has_docs = manager.has_documents(test_user_id, test_session_id)
    print(f"   {'✅' if has_docs else '❌'} Has documents: {has_docs}")
    
    # Test retrieval
    print("\n6. Test document retrieval:")
    try:
        query = "What are the key topics in computer science?"
        results = retriever.get_relevant_documents(query)
        print(f"   ✅ Retrieved {len(results)} documents")
        if results:
            print(f"   Top result preview: {results[0].page_content[:100]}...")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test convenience functions
    print("\n7. Test convenience functions:")
    retriever2 = get_session_retriever(test_user_id, test_session_id)
    has_docs2 = has_session_documents(test_user_id, test_session_id)
    print(f"   ✅ get_session_retriever: {retriever2 is not None}")
    print(f"   ✅ has_session_documents: {has_docs2}")
    
    # Cleanup
    print("\n8. Cleanup test data:")
    deleted = manager.delete_session_store(test_user_id, test_session_id)
    print(f"   {'✅' if deleted else '❌'} Deleted: {deleted}")
    
    print("\n✅ Session retriever tests complete\n")


def test_end_to_end():
    """Test complete workflow"""
    from multiagent.utils.document_parser import parse_document
    from multiagent.memory.retriever_manager import get_session_retriever_manager
    
    print("=" * 60)
    print("TEST 3: End-to-End Workflow")
    print("=" * 60)
    
    # Simulate uploaded file
    print("\n1. Simulate file upload:")
    file_content = b"""
    Data Structures Course - Lecture 1
    
    Topics Covered:
    - Arrays and Lists
    - Time Complexity Analysis
    - Big O Notation
    
    Arrays:
    An array is a collection of elements stored in contiguous memory.
    Access time: O(1)
    Search time: O(n)
    
    Lists:
    A list is a dynamic data structure that can grow and shrink.
    Common operations: append, insert, remove, search
    """
    filename = "lecture1.txt"
    
    # Parse document
    print("\n2. Parse document:")
    try:
        text = parse_document(file_content, filename)
        print(f"   ✅ Parsed {len(text)} characters")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Ingest into vector store
    print("\n3. Ingest into vector store:")
    manager = get_session_retriever_manager()
    user_id = 888
    session_id = "e2e_test_session"
    
    try:
        result = manager.ingest_document(user_id, session_id, text, filename)
        print(f"   ✅ Created {result['chunks_created']} chunks")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Get retriever
    print("\n4. Get retriever:")
    retriever = manager.get_session_retriever(user_id, session_id)
    if retriever:
        print(f"   ✅ Retriever ready")
    else:
        print(f"   ❌ No retriever")
        return
    
    # Simulate agent queries
    print("\n5. Simulate agent queries:")
    queries = [
        "What is the time complexity of array access?",
        "What topics were covered in the lecture?",
        "What is the difference between arrays and lists?"
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"\n   Query {i}: {query}")
        try:
            results = retriever.get_relevant_documents(query)
            if results:
                print(f"   ✅ Found {len(results)} relevant chunks")
                print(f"      Best match: {results[0].page_content[:80]}...")
            else:
                print(f"   ❌ No results")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Cleanup
    print("\n6. Cleanup:")
    deleted = manager.delete_session_store(user_id, session_id)
    print(f"   {'✅' if deleted else '❌'} Cleaned up test data")
    
    print("\n✅ End-to-end workflow complete\n")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("FILE UPLOAD SYSTEM - INTEGRATION TESTS")
    print("=" * 60 + "\n")
    
    try:
        # Test 1: Document Parser
        test_document_parser()
        
        # Test 2: Session Retriever Manager
        test_session_retriever()
        
        # Test 3: End-to-End Workflow
        test_end_to_end()
        
        print("=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY ✅")
        print("=" * 60 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user\n")
    except Exception as e:
        print(f"\n\n❌ Test suite failed with error: {e}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
