"""Memory management for multi-agent conversation system."""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import threading
import json


@dataclass
class ConversationTurn:
    """Represents a single turn in a conversation."""
    user_message: str
    agent_response: str
    timestamp: datetime
    route: List[str]  # Which agents were used
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "user_message": self.user_message,
            "agent_response": self.agent_response,
            "timestamp": self.timestamp.isoformat(),
            "route": self.route
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ConversationTurn":
        """Create from dictionary."""
        return cls(
            user_message=data["user_message"],
            agent_response=data["agent_response"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            route=data.get("route", [])
        )


class MemoryManager:
    """Manages conversation memory for multiple users/sessions."""
    
    def __init__(self, max_history_length: int = 10):
        """
        Initialize memory manager.
        
        Args:
            max_history_length: Maximum number of conversation turns to keep per session
        """
        self.max_history_length = max_history_length
        self._sessions: Dict[str, List[ConversationTurn]] = {}
        self._lock = threading.RLock()  # Thread-safe operations
    
    def get_history(self, session_id: str) -> List[ConversationTurn]:
        """
        Get conversation history for a session.
        
        Args:
            session_id: Unique identifier for the session
            
        Returns:
            List of conversation turns, ordered chronologically
        """
        with self._lock:
            return self._sessions.get(session_id, []).copy()
    
    def add_turn(self, session_id: str, user_message: str, agent_response: str, route: List[str] = None) -> None:
        """
        Add a new conversation turn to the session history.
        
        Args:
            session_id: Unique identifier for the session
            user_message: The user's question/message
            agent_response: The agent's response
            route: List of agents/nodes that were used
        """
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = []
            
            turn = ConversationTurn(
                user_message=user_message,
                agent_response=agent_response,
                timestamp=datetime.now(),
                route=route or []
            )
            
            self._sessions[session_id].append(turn)
            
            # Trim history if it exceeds max length
            if len(self._sessions[session_id]) > self.max_history_length:
                self._sessions[session_id] = self._sessions[session_id][-self.max_history_length:]
    
    def clear_session(self, session_id: str) -> None:
        """
        Clear conversation history for a session.
        
        Args:
            session_id: Unique identifier for the session
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
    
    def get_session_count(self) -> int:
        """Get the number of active sessions."""
        with self._lock:
            return len(self._sessions)
    
    def get_all_sessions(self) -> List[str]:
        """Get list of all active session IDs."""
        with self._lock:
            return list(self._sessions.keys())
    
    def get_context_string(self, session_id: str, include_routes: bool = False) -> str:
        """
        Get conversation history as a formatted string for context.
        
        Args:
            session_id: Unique identifier for the session
            include_routes: Whether to include routing information
            
        Returns:
            Formatted string with conversation history
        """
        history = self.get_history(session_id)
        if not history:
            return ""
        
        context_parts = ["Previous conversation:"]
        for i, turn in enumerate(history, 1):
            context_parts.append(f"Q{i}: {turn.user_message}")
            response = turn.agent_response
            if include_routes and turn.route:
                response += f" [via: {' -> '.join(turn.route)}]"
            context_parts.append(f"A{i}: {response}")
        
        return "\n".join(context_parts)
    
    def get_last_context(self, session_id: str, last_n: int = 3) -> str:
        """
        Get the last N conversation turns as context.
        
        Args:
            session_id: Unique identifier for the session
            last_n: Number of recent turns to include
            
        Returns:
            Formatted string with recent conversation history
        """
        history = self.get_history(session_id)
        if not history:
            return ""
        
        recent_history = history[-last_n:] if len(history) > last_n else history
        context_parts = []
        
        for turn in recent_history:
            context_parts.append(f"User: {turn.user_message}")
            context_parts.append(f"Assistant: {turn.agent_response}")
        
        if context_parts:
            return "Recent conversation:\n" + "\n".join(context_parts) + "\n\nCurrent question:"
        return ""
    
    def export_session(self, session_id: str) -> str:
        """
        Export session history as JSON string.
        
        Args:
            session_id: Unique identifier for the session
            
        Returns:
            JSON string with session data
        """
        history = self.get_history(session_id)
        data = {
            "session_id": session_id,
            "turns": [turn.to_dict() for turn in history],
            "exported_at": datetime.now().isoformat()
        }
        return json.dumps(data, indent=2)
    
    def import_session(self, session_data: str) -> str:
        """
        Import session history from JSON string.
        
        Args:
            session_data: JSON string with session data
            
        Returns:
            The imported session ID
        """
        data = json.loads(session_data)
        session_id = data["session_id"]
        
        with self._lock:
            self._sessions[session_id] = [
                ConversationTurn.from_dict(turn_data) 
                for turn_data in data["turns"]
            ]
        
        return session_id


# Global memory manager instance
memory_manager = MemoryManager()