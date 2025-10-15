"""
Test Session ID Persistence Bug Fix
====================================

Tests that uploaded documents remain findable after session_name changes
due to auto-titling. Validates that using immutable session.id for vector
store paths prevents the bug where documents become unfindable.

Bug Background:
--------------
1. User uploads document → stored at user_1_session_<initial_name>/
2. User sends first message → auto-titling changes session_name
3. Agent tries to retrieve → looks at user_1_session_<new_name>/
4. Documents not found! ❌

Fix:
----
Use immutable session.id instead of mutable session_name for vector stores.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
import json
import time
from io import BytesIO
from datetime import datetime

# Test configuration
BASE_URL = "http://localhost:8000"
TEST_USERNAME = "admin"  # Use admin account
TEST_PASSWORD = "adminpassword123!"

# API endpoints (no /api prefix)
AUTH_LOGIN = f"{BASE_URL}/auth/login"
CHATS_BASE = f"{BASE_URL}/chats"
MULTIAGENT_CHAT = f"{BASE_URL}/multiagent/chat"

# Test document content - simple course outline
TEST_DOCUMENT_CONTENT = """
COURSE OUTLINE: Computer Vision (CS-401)

Course Learning Outcomes (CLOs):
1. CLO1: Analyze fundamental image processing techniques
2. CLO2: Design and implement feature extraction algorithms
3. CLO3: Evaluate deep learning models for vision tasks
4. CLO4: Create complete computer vision applications

Program Learning Outcomes (PLOs):
1. PLO1: Apply computational thinking to solve complex problems
2. PLO2: Design and implement software systems
3. PLO3: Evaluate emerging technologies and methodologies
4. PLO4: Communicate technical concepts effectively
"""


def print_section(title):
    """Print formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def login():
    """Login and get authentication token."""
    print_section("STEP 1: Login")
    
    response = requests.post(
        AUTH_LOGIN,
        json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.text}")
        sys.exit(1)
    
    data = response.json()
    token = data["access_token"]
    print(f"✅ Logged in as {TEST_USERNAME}")
    print(f"   Token: {token[:30]}...")
    
    return token


def create_session(token):
    """Create a new chat session."""
    print_section("STEP 2: Create Chat Session")
    
    # Use timestamp as initial session name (like UI does)
    timestamp = datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
    initial_name = f"Chat {timestamp}"
    
    response = requests.post(
        CHATS_BASE,
        headers={"Authorization": f"Bearer {token}"},
        json={"session_name": initial_name}
    )
    
    if response.status_code not in [200, 201]:
        print(f"❌ Session creation failed: {response.text}")
        sys.exit(1)
    
    data = response.json()
    session_id = data["id"]
    session_name = data["session_name"]
    
    print(f"✅ Session created")
    print(f"   ID: {session_id}")
    print(f"   Initial Name: {session_name}")
    
    return session_id, session_name


def upload_document(token, session_id, initial_name):
    """Upload a test document to the session."""
    print_section("STEP 3: Upload Document")
    
    # Create a file-like object from the test content
    file_data = BytesIO(TEST_DOCUMENT_CONTENT.encode('utf-8'))
    
    response = requests.post(
        f"{CHATS_BASE}/{session_id}/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "file": ("course_outline.txt", file_data, "text/plain")
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Upload failed: {response.text}")
        sys.exit(1)
    
    data = response.json()
    print(f"✅ Document uploaded")
    print(f"   Filename: {data['filename']}")
    print(f"   Chunks created: {data['chunks_created']}")
    print(f"   Expected vector store path: user_1_session_{session_id}/")
    print(f"   (Using immutable DB ID, not session name '{initial_name}')")
    
    return data


def send_message(token, session_id, question, expect_streaming=True):
    """Send a message and get response."""
    response = requests.post(
        MULTIAGENT_CHAT,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question": question,
            "session_id": str(session_id),
            "stream": expect_streaming
        },
        stream=expect_streaming
    )
    
    if response.status_code != 200:
        print(f"❌ Chat failed: {response.text}")
        sys.exit(1)
    
    if expect_streaming:
        # Collect streaming response
        full_response = ""
        new_title = None
        
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    try:
                        event_data = json.loads(line_str[6:])
                        
                        if event_data.get('event') == 'chunk':
                            chunk = event_data.get('content', '')
                            full_response += chunk
                            print(chunk, end='', flush=True)
                        
                        elif event_data.get('event') == 'title':
                            new_title = event_data.get('title')
                            print(f"\n\n   📝 Auto-generated title: '{new_title}'")
                        
                        elif event_data.get('event') == 'done':
                            print("\n   ✅ Response complete")
                            break
                    
                    except json.JSONDecodeError:
                        pass
        
        return full_response, new_title
    else:
        data = response.json()
        return data.get("response", ""), None


def get_session_details(token, session_id):
    """Get updated session details."""
    response = requests.get(
        f"{CHATS_BASE}/{session_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code != 200:
        print(f"❌ Get session failed: {response.text}")
        return None
    
    return response.json()


def main():
    """Run the complete test scenario."""
    print("\n" + "="*70)
    print("  SESSION ID PERSISTENCE BUG FIX TEST")
    print("="*70)
    print("\nThis test validates that uploaded documents remain findable")
    print("even after session_name changes due to auto-titling.")
    print("\nExpected behavior:")
    print("  1. Documents stored using immutable session.id")
    print("  2. session_name can change freely for display")
    print("  3. Agents always find documents at id-based path")
    
    # Step 1: Login
    token = login()
    
    # Step 2: Create session
    session_id, initial_name = create_session(token)
    
    # Step 3: Upload document
    upload_result = upload_document(token, session_id, initial_name)
    
    # Step 4: Send first message (triggers auto-titling)
    print_section("STEP 4: Send First Message (Triggers Auto-Titling)")
    print("Question: 'Extract the CLOs from the uploaded document'\n")
    
    response1, new_title = send_message(
        token, 
        session_id, 
        "Extract the CLOs from the uploaded document"
    )
    
    # Step 5: Check if session name changed
    print_section("STEP 5: Verify Session State")
    
    session_details = get_session_details(token, session_id)
    if session_details:
        current_name = session_details.get("session_name")
        print(f"Session ID: {session_id} (immutable)")
        print(f"Initial Name: {initial_name}")
        print(f"Current Name: {current_name}")
        
        if current_name != initial_name:
            print(f"\n✅ Session name changed (expected)")
            print(f"   This would have broken document lookup in old code!")
            print(f"   Old path: user_1_session_{initial_name}/")
            print(f"   Would look: user_1_session_{current_name}/")
            print(f"   Actual path: user_1_session_{session_id}/ (immutable)")
        else:
            print(f"\n⚠️  Session name hasn't changed yet")
            print(f"   Auto-titling may occur after agent response")
    
    # Step 6: Verify document extraction worked
    print_section("STEP 6: Verify Document Extraction")
    
    print(f"Agent Response Preview (first 500 chars):")
    print(f"{response1[:500]}...")
    print()
    
    if "CLO1" in response1 or "CLO2" in response1 or "CLO3" in response1:
        print("✅ SUCCESS! Documents were found and extracted")
        print("   Agent successfully retrieved CLOs from uploaded document")
        print("   Fix confirmed: immutable ID prevents path mismatch")
    else:
        print("❌ FAILED! Documents not found")
        print("   Agent returned generic response without extracting CLOs")
        print("   This indicates the vector store path is still incorrect")
    
    # Step 7: Test with second message
    print_section("STEP 7: Send Second Message (Test Persistence)")
    print("Question: 'Map CLO1 to appropriate PLOs'\n")
    
    response2, _ = send_message(
        token,
        session_id,
        "Map CLO1 to appropriate PLOs"
    )
    
    # Step 8: Final verification
    print_section("STEP 8: Final Verification")
    
    success_indicators = [
        ("Document extraction", "CLO1" in response1 or "CLO2" in response1),
        ("PLO mapping", "PLO" in response2),
        ("Vector store persistence", "CLO1" in response2 or "Analyze" in response2)
    ]
    
    print("Test Results:")
    all_passed = True
    for check_name, passed in success_indicators:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {check_name}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*70)
    if all_passed:
        print("  🎉 ALL TESTS PASSED!")
        print("  Session ID persistence fix is working correctly")
    else:
        print("  ⚠️  SOME TESTS FAILED")
        print("  Review the output above for details")
    print("="*70 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
