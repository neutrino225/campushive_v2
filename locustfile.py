from locust import HttpUser, task, between
import random
import string

class CampusHiveUser(HttpUser):
    wait_time = between(1, 5)
    token = None
    user_id = None
    current_session_id = None

    def on_start(self):
        """Register and Login to get token"""
        username = self._random_string(8)
        password = "Password123!"
        email = f"{username}@test.com"
        
        # Signup
        signup_success = False
        with self.client.post("/auth/signup", json={
            "username": username,
            "email": email,
            "password": password
        }, catch_response=True) as response:
            if response.status_code == 201:
                data = response.json()
                self.token = data["access_token"]
                self.user_id = data["user"]["id"]
                signup_success = True
            elif "already registered" in response.text:
                # If user exists, we don't mark as failure, just proceed to login
                response.success()
            else:
                response.failure(f"Signup failed: {response.text}")

        if not signup_success:
            self._login(username, password)

    def _login(self, username, password):
        with self.client.post("/auth/login", json={
            "username": username,
            "password": password
        }, catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                self.token = data["access_token"]
                self.user_id = data["user"]["id"]
            else:
                response.failure(f"Login failed: {response.text}")

    @task(3)
    def view_sessions(self):
        """List all chat sessions"""
        if not self.token: return
        headers = {"Authorization": f"Bearer {self.token}"}
        self.client.get("/chats", headers=headers)

    @task(1)
    def create_session(self):
        """Create a new chat session"""
        if not self.token: return
        headers = {"Authorization": f"Bearer {self.token}"}
        with self.client.post("/chats", json={
            "session_name": f"Load Test Session {self._random_string(4)}"
        }, headers=headers, catch_response=True) as response:
            if response.status_code == 201:
                self.current_session_id = response.json()["id"]
                response.success()
            else:
                response.failure(f"Create session failed: {response.text}")

    @task(5)
    def chat_interaction(self):
        """Send a message to the AI agent"""
        if not self.token: return
        
        if not self.current_session_id:
            # Try to get an existing session
            headers = {"Authorization": f"Bearer {self.token}"}
            # We don't necessarily need catch_response here if we don't manually mark success/fail based on content
            # But let's keep it simple.
            response = self.client.get("/chats", headers=headers)
            if response.status_code == 200:
                sessions = response.json()
                if sessions:
                    self.current_session_id = random.choice(sessions)["id"]
            
            if not self.current_session_id:
                 # Create a session. Note: calling the task method directly. 
                 # Since create_session uses its own with-block, this is safe.
                 self.create_session()
            
            if not self.current_session_id:
                return # Still no session, skip
            
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "question": "What courses are available in Computer Science?",
            "session_id": self.current_session_id,
            "stream": False # Disable streaming for easier load testing measurement
        }
        
        # This is expected to be slow
        with self.client.post("/multiagent/chat", json=payload, headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 500:
                response.failure("Internal Server Error during chat")
            else:
                response.failure(f"Chat failed with status {response.status_code}")

    def _random_string(self, length):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))