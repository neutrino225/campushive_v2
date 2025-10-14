"""
State schema for planning-based main supervisor.
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass, field

root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

try:
    from typing_extensions import TypedDict
except ImportError:
    from typing import TypedDict


@dataclass
class SubTask:
    """Represents a subtask in the planning process."""
    id: int
    agent: str  # Which agent to call
    query: str  # What to ask the agent
    status: Literal["pending", "in_progress", "completed", "failed"]
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "query": self.query,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count
        }


class PlanningState(TypedDict):
    """Extended state for planning-based supervisor."""
    # Original fields
    question: str
    result: str
    route: List[str]
    session_id: str
    conversation_history: List
    user_role: str
    messages: List
    
    # Planning fields
    scratchpad: List[str]  # LLM's reasoning trace (visible to user)
    plan: List[Dict]  # List of SubTask dicts
    current_task_id: int  # Which task is being executed
    intermediate_results: Dict[str, str]  # task_id -> result mapping
    
    # Human-in-the-loop
    awaiting_user_input: bool  # Flag to pause execution
    user_input_question: str  # Question to ask user
    user_input_context: Dict  # Context about why we need input
    
    # Execution control
    planning_mode: bool  # True for complex queries, False for simple
    max_retries: int  # Maximum retry attempts per task
    total_api_calls: int  # Track API usage
