# Locust Load Testing Plan for CampusHive API

This document outlines the strategy for load testing the CampusHive API using [Locust](https://locust.io/). The goal is to evaluate the system's performance under concurrent user load, specifically focusing on the multi-agent chat capabilities and authentication flows.

## 1. Objectives

- **Benchmark Performance:** Determine the baseline response times for critical endpoints.
- **Stress Test:** Identify the maximum number of concurrent users the system can handle before degradation.
- **Bottleneck Identification:** Pinpoint slow endpoints (likely `/multiagent/chat` due to LLM inference).
- **Stability:** Ensure the API remains stable under sustained load.

## 2. Target Endpoints

### Critical Paths (High Priority)
- **Authentication:**
  - `POST /auth/signup` (User creation)
  - `POST /auth/login` (Token generation)
  - `GET /auth/me` (Token validation)
- **Chat Interaction:**
  - `POST /multiagent/chat` (The core AI processing loop)
  - `GET /chats/{session_id}` (Loading conversation context)
  - `GET /chats` (Listing sessions)

### Secondary Paths (Medium Priority)
- **Session Management:**
  - `POST /chats` (Creating empty sessions)
  - `PUT /chats/{session_id}` (Renaming sessions)
- **Admin/System:**
  - `GET /admin/health`
  - `GET /admin/health/vector-stores`

## 3. User Profiles & Scenarios

We will define a primary `StandardUser` class to simulate typical student behavior.

### Profile: `StandardUser`
**Behavior:**
1.  **Start:** Registers a new random account or logs in with existing credentials to obtain a JWT.
2.  **Task Loop:**
    - **Browse:** Checks list of chat sessions.
    - **Chat:** Creates a new session or selects an existing one.
    - **Interact:** Sends questions to the multi-agent system (`/multiagent/chat`) and waits for the response.
    - **Review:** Fetches chat history.

**Wait Time:** 
- `between(1, 5)` seconds (Simulating user think time).

### Scenario 1: New User Onboarding (Burst)
- **Focus:** High rate of `signup` and initial `create_chat_session` calls.
- **Goal:** Test database write performance and concurrency handling during user spikes.

### Scenario 2: Active Conversation (Sustained)
- **Focus:** Heavy usage of `POST /multiagent/chat`.
- **Goal:** Test the limits of the multi-agent supervisor graph and LLM integration.

## 4. Implementation Details

### `locustfile.py` Structure

```python
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
        with self.client.post("/auth/signup", json={
            "username": username,
            "email": email,
            "password": password
        }, catch_response=True) as response:
            if response.status_code == 201:
                data = response.json()
                self.token = data["access_token"]
                self.user_id = data["user"]["id"]
            else:
                response.failure(f"Signup failed: {response.text}")

    @task(3)
    def view_sessions(self):
        """List all chat sessions"""
        headers = {"Authorization": f"Bearer {self.token}"}
        self.client.get("/chats", headers=headers)

    @task(1)
    def create_session(self):
        """Create a new chat session"""
        headers = {"Authorization": f"Bearer {self.token}"}
        response = self.client.post("/chats", json={
            "session_name": "Load Test Session"
        }, headers=headers)
        if response.status_code == 201:
            self.current_session_id = response.json()["id"]

    @task(5)
    def chat_interaction(self):
        """Send a message to the AI agent"""
        if not self.current_session_id:
            self.create_session()
            
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
```

## 5. Environment & Configuration

- **Host:** `http://localhost:8000` (Local) or Staging URL.
- **Database:** Ensure the database (SQLite/Postgres) is reset or can handle the influx of test users.
- **LLM/API Keys:** **Critical Warning:** Load testing the `/multiagent/chat` endpoint will consume real tokens if connected to a live LLM provider (OpenAI/Gemini). 
    - **Recommendation:** Mock the LLM responses or the `supervisor_graph` for pure API load testing, or set strict limits if testing full integration.

## 6. Execution Steps

1.  **Install Locust:**
    ```bash
    pip install locust
    ```

2.  **Run Headless (CI/CD):**
    ```bash
    locust -f locustfile.py --headless -u 50 -r 5 --run-time 5m --host http://localhost:8000
    ```
    - `-u 50`: 50 total users.
    - `-r 5`: Spawn 5 users per second.
    - `--run-time 5m`: Run for 5 minutes.

3.  **Run with UI:**
    ```bash
    locust -f locustfile.py --host http://localhost:8000
    ```
    - Access dashboard at `http://localhost:8089`.

## 7. Metrics to Monitor

| Metric | Target | Threshold (Failure) |
| :--- | :--- | :--- |
| **Auth Response Time** | < 200ms | > 1000ms |
| **Chat Response Time** | < 5000ms (highly variable based on LLM) | > 30000ms (Timeout) |
| **Error Rate** | < 1% | > 5% |
| **RPS (Throughput)** | N/A (Baseline) | N/A |
