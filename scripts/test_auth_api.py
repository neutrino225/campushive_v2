#!/usr/bin/env python3
"""
Test script for authentication and chat management APIs.
"""
import requests
import json
from typing import Dict, Optional

BASE_URL = "http://localhost:8000"


class APITester:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.user_id: Optional[int] = None
        
    def headers(self) -> Dict[str, str]:
        """Get headers with auth token if available."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    def test_signup(self, username: str, email: str, password: str):
        """Test user signup."""
        print(f"\n{'='*60}")
        print("TEST: User Signup")
        print(f"{'='*60}")
        
        url = f"{self.base_url}/auth/signup"
        data = {
            "username": username,
            "email": email,
            "password": password
        }
        
        response = requests.post(url, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 201:
            result = response.json()
            self.token = result["access_token"]
            self.user_id = result["user"]["id"]
            print(f"✓ Signup successful! Token saved.")
        else:
            print(f"✗ Signup failed!")
        
        return response
    
    def test_login(self, username: str, password: str):
        """Test user login."""
        print(f"\n{'='*60}")
        print("TEST: User Login")
        print(f"{'='*60}")
        
        url = f"{self.base_url}/auth/login"
        data = {
            "username": username,
            "password": password
        }
        
        response = requests.post(url, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            result = response.json()
            self.token = result["access_token"]
            self.user_id = result["user"]["id"]
            print(f"✓ Login successful! Token saved.")
        else:
            print(f"✗ Login failed!")
        
        return response
    
    def test_get_current_user(self):
        """Test getting current user info."""
        print(f"\n{'='*60}")
        print("TEST: Get Current User")
        print(f"{'='*60}")
        
        url = f"{self.base_url}/auth/me"
        response = requests.get(url, headers=self.headers())
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        return response
    
    def test_create_chat_session(self, session_name: str):
        """Test creating a chat session."""
        print(f"\n{'='*60}")
        print("TEST: Create Chat Session")
        print(f"{'='*60}")
        
        url = f"{self.base_url}/chats"
        data = {"session_name": session_name}
        
        response = requests.post(url, json=data, headers=self.headers())
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        return response
    
    def test_list_chat_sessions(self):
        """Test listing chat sessions."""
        print(f"\n{'='*60}")
        print("TEST: List Chat Sessions")
        print(f"{'='*60}")
        
        url = f"{self.base_url}/chats"
        response = requests.get(url, headers=self.headers())
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        return response
    
    def test_add_message(self, session_id: int, content: str):
        """Test adding a message to a chat session."""
        print(f"\n{'='*60}")
        print("TEST: Add Message to Chat Session")
        print(f"{'='*60}")
        
        url = f"{self.base_url}/chats/{session_id}/messages"
        data = {"content": content}
        
        response = requests.post(url, json=data, headers=self.headers())
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        return response
    
    def test_get_chat_session(self, session_id: int):
        """Test getting a chat session with messages."""
        print(f"\n{'='*60}")
        print("TEST: Get Chat Session with Messages")
        print(f"{'='*60}")
        
        url = f"{self.base_url}/chats/{session_id}"
        response = requests.get(url, headers=self.headers())
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        return response
    
    def test_admin_list_users(self):
        """Test listing users (admin only)."""
        print(f"\n{'='*60}")
        print("TEST: List Users (Admin)")
        print(f"{'='*60}")
        
        url = f"{self.base_url}/admin/users"
        response = requests.get(url, headers=self.headers())
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        return response
    
    def test_admin_update_role(self, user_id: int, new_role: str):
        """Test updating user role (admin only)."""
        print(f"\n{'='*60}")
        print("TEST: Update User Role (Admin)")
        print(f"{'='*60}")
        
        url = f"{self.base_url}/admin/users/{user_id}/role"
        data = {"role": new_role}
        
        response = requests.put(url, json=data, headers=self.headers())
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        return response


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("AUTHENTICATION AND CHAT MANAGEMENT API TESTS")
    print("="*60)
    
    tester = APITester()
    
    # Test 1: Sign up a new student user
    tester.test_signup("john_doe", "john@example.com", "Password123!")
    
    # Test 2: Get current user info
    tester.test_get_current_user()
    
    # Test 3: Create a chat session
    response = tester.test_create_chat_session("My First Chat")
    if response.status_code == 201:
        session_id = response.json()["id"]
        
        # Test 4: Add a message to the session
        tester.test_add_message(session_id, "Hello, this is my first message!")
        
        # Test 5: Get the chat session with messages
        tester.test_get_chat_session(session_id)
    
    # Test 6: List all chat sessions
    tester.test_list_chat_sessions()
    
    # Test 7: Try to access admin endpoint (should fail)
    tester.test_admin_list_users()
    
    # Test 8: Login as admin
    admin_tester = APITester()
    admin_tester.test_login("admin", "Admin123!")
    
    # Test 9: List all users as admin
    admin_tester.test_admin_list_users()
    
    # Test 10: Update user role
    if tester.user_id:
        admin_tester.test_admin_update_role(tester.user_id, "faculty")
    
    # Test 11: Logout
    print(f"\n{'='*60}")
    print("TEST: Logout")
    print(f"{'='*60}")
    url = f"{BASE_URL}/auth/logout"
    response = requests.post(url, headers=tester.headers())
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    print(f"\n{'='*60}")
    print("ALL TESTS COMPLETED")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
