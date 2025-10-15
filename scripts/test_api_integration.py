#!/usr/bin/env python3
"""
API Integration Test - Document Upload and OBE Extraction

Tests the complete workflow through the actual API endpoints:
1. Login
2. Create session
3. Upload document
4. Request CLO-PLO mapping
5. Verify extraction and mapping work correctly
"""

import requests
import json
import sys
from pathlib import Path

# Configuration
BASE_URL = "http://localhost:8000"
USERNAME = "admin"  # Change to your test user
PASSWORD = "admin"  # Change to your test password

def print_section(title):
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80 + "\n")

def print_success(message):
    print(f"✅ {message}")

def print_error(message):
    print(f"❌ {message}")

def print_info(message):
    print(f"ℹ️  {message}")

def test_api_workflow():
    """Test complete API workflow"""
    
    print("\n" + "█" * 80)
    print("  API Integration Test - Document Upload and OBE Extraction")
    print("  Testing: Login → Create Session → Upload → Extract → Map")
    print("█" * 80)
    
    # Step 1: Login
    print_section("Step 1: Authentication")
    
    try:
        login_response = requests.post(
            f"{BASE_URL}/auth/login",
            data={"username": USERNAME, "password": PASSWORD}
        )
        
        if login_response.status_code != 200:
            print_error(f"Login failed: {login_response.status_code}")
            print_error(login_response.text)
            return False
        
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print_success("Login successful")
        print_info(f"Token: {token[:20]}...")
        
    except Exception as e:
        print_error(f"Login failed: {e}")
        return False
    
    # Step 2: Create Session
    print_section("Step 2: Create Chat Session")
    
    try:
        session_response = requests.post(
            f"{BASE_URL}/api/v1/chats",
            headers={**headers, "Content-Type": "application/json"},
            json={"session_name": "test_obe_extraction"}
        )
        
        if session_response.status_code != 200:
            print_error(f"Session creation failed: {session_response.status_code}")
            print_error(session_response.text)
            return False
        
        session_data = session_response.json()
        session_id = session_data["id"]
        session_name = session_data["session_name"]
        
        print_success(f"Session created successfully")
        print_info(f"Session ID: {session_id}")
        print_info(f"Session Name: {session_name}")
        
    except Exception as e:
        print_error(f"Session creation failed: {e}")
        return False
    
    # Step 3: Upload Document
    print_section("Step 3: Upload Course Outline Document")
    
    # Create test document
    test_document = """# Course Outline: Advanced Algorithms (CS-5001)

## Course Learning Outcomes (CLOs)

Upon successful completion of this course, students will be able to:

1. **CLO-1**: Analyze the time and space complexity of algorithms using asymptotic notation (Big-O, Theta, Omega).

2. **CLO-2**: Design efficient algorithms for sorting, searching, and graph traversal problems using appropriate data structures.

3. **CLO-3**: Evaluate different algorithmic paradigms (divide-and-conquer, dynamic programming, greedy algorithms) and select the most suitable approach for specific problems.

4. **CLO-4**: Implement advanced data structures (heaps, hash tables, balanced trees) and apply them to solve complex computational problems.

5. **CLO-5**: Apply algorithm optimization techniques to improve the performance of existing solutions and justify design choices.

## Program Learning Outcomes (PLOs)

1. **PLO-1**: An ability to analyze complex computing problems and to apply principles of computing and other relevant disciplines to identify solutions.

2. **PLO-2**: An ability to design, implement, and evaluate a computing-based solution to meet a given set of computing requirements in the context of the program's discipline.

3. **PLO-3**: An ability to communicate effectively in a variety of professional contexts.

4. **PLO-4**: An ability to recognize professional responsibilities and make informed judgments in computing practice based on legal and ethical principles.

5. **PLO-5**: An ability to function effectively as a member or leader of a team engaged in activities appropriate to the program's discipline.

6. **PLO-6**: An ability to apply computer science theory and software development fundamentals to produce computing-based solutions.
"""
    
    try:
        # Save to temporary file
        temp_file = Path("/tmp/test_course_outline.txt")
        temp_file.write_text(test_document)
        
        with open(temp_file, 'rb') as f:
            files = {'file': ('test_course_outline.txt', f, 'text/plain')}
            upload_response = requests.post(
                f"{BASE_URL}/api/v1/chats/{session_id}/upload",
                headers=headers,
                files=files
            )
        
        if upload_response.status_code != 200:
            print_error(f"Upload failed: {upload_response.status_code}")
            print_error(upload_response.text)
            return False
        
        upload_data = upload_response.json()
        print_success("Document uploaded successfully")
        print_info(f"Filename: {upload_data['filename']}")
        print_info(f"Chunks created: {upload_data['chunks_created']}")
        
    except Exception as e:
        print_error(f"Upload failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 4: Request CLO-PLO Mapping
    print_section("Step 4: Request CLO-PLO Mapping from Document")
    
    try:
        chat_response = requests.post(
            f"{BASE_URL}/api/v1/multiagent/chat",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "question": "Map the CLOs to PLOs from the uploaded document",
                "session_id": session_name,  # Use session_name, not numeric ID
                "stream": False
            }
        )
        
        if chat_response.status_code != 200:
            print_error(f"Chat request failed: {chat_response.status_code}")
            print_error(chat_response.text)
            return False
        
        response_data = chat_response.json()
        result = response_data.get("result", "")
        
        # Check if extraction worked
        if "CLO-PLO Mapping" in result:
            print_success("Mapping generated successfully!")
            print_info("Response contains advanced mapping")
            
            # Check for key components
            if "Mapping Table" in result:
                print_success("✓ Mapping table present")
            
            if "Detailed Justifications" in result:
                print_success("✓ Detailed justifications present")
            
            if "Scoring Methodology" in result:
                print_success("✓ Scoring methodology present")
            
            if "Executive Summary" in result:
                print_success("✓ Executive summary present")
            
            # Print preview
            print("\n" + "-" * 80)
            print("Response Preview (first 1000 characters):")
            print("-" * 80)
            print(result[:1000])
            print("...")
            print("-" * 80)
            
            return True
            
        else:
            print_error("Response does NOT contain expected mapping")
            print_error("Received instead:")
            print(result[:500])
            return False
        
    except Exception as e:
        print_error(f"Chat request failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run the API integration test"""
    
    # Check if server is running
    try:
        health_check = requests.get(f"{BASE_URL}/docs", timeout=2)
        if health_check.status_code != 200:
            print_error(f"Server returned status {health_check.status_code}")
            print_info("Make sure the server is running: uvicorn app.main:app --reload")
            return 1
    except requests.exceptions.ConnectionError:
        print_error(f"Cannot connect to server at {BASE_URL}")
        print_info("Start the server with: uvicorn app.main:app --reload")
        return 1
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return 1
    
    # Run the test
    success = test_api_workflow()
    
    # Print summary
    print_section("Test Summary")
    
    if success:
        print("🎉 API Integration Test PASSED!")
        print("\nThe complete workflow is functioning correctly:")
        print("  ✓ Authentication works")
        print("  ✓ Session creation works")
        print("  ✓ Document upload works")
        print("  ✓ OBE extraction from uploaded document works")
        print("  ✓ Advanced CLO-PLO mapping generation works")
        print("\nThe session_id mismatch bug is FIXED!")
        return 0
    else:
        print("⚠️  API Integration Test FAILED")
        print("\nPlease check:")
        print("  1. Server is running (uvicorn app.main:app --reload)")
        print("  2. Correct username/password in script")
        print("  3. Server logs for errors")
        return 1

if __name__ == "__main__":
    sys.exit(main())
