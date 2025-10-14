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
    """Manages conversation memory for multiple users/sessions with safeguards."""
    
    def __init__(self, max_history_length: int = 50, max_sessions: int = 1000, session_ttl_hours: int = 24):
        """
        Initialize memory manager with safeguards.
        
        Args:
            max_history_length: Maximum number of conversation turns to keep per session
            max_sessions: Maximum number of concurrent sessions to prevent memory overflow
            session_ttl_hours: Time-to-live for inactive sessions in hours
        """
        self.max_history_length = max_history_length
        self.max_sessions = max_sessions
        self.session_ttl_hours = session_ttl_hours
        self._sessions: Dict[str, List[ConversationTurn]] = {}
        self._session_last_access: Dict[str, datetime] = {}  # Track last access for TTL
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
            # Update last access time
            self._session_last_access[session_id] = datetime.now()
            return self._sessions.get(session_id, []).copy()
    
    def add_turn(self, session_id: str, user_message: str, agent_response: str, route: List[str] = None) -> None:
        """
        Add a new conversation turn to the session history with safeguards.
        
        Args:
            session_id: Unique identifier for the session
            user_message: The user's question/message
            agent_response: The agent's response
            route: List of agents/nodes that were used
        """
        with self._lock:
            # Check if we need to cleanup old sessions
            self._cleanup_stale_sessions()
            
            # Enforce max sessions limit (evict oldest if needed)
            if len(self._sessions) >= self.max_sessions and session_id not in self._sessions:
                self._evict_oldest_session()
            
            if session_id not in self._sessions:
                self._sessions[session_id] = []
            
            # Update last access time
            self._session_last_access[session_id] = datetime.now()
            
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
    
    def _cleanup_stale_sessions(self) -> int:
        """
        Remove sessions that haven't been accessed for TTL hours.
        Called automatically by add_turn. Thread-safe (assumes lock is held).
        
        Returns:
            Number of sessions removed
        """
        from datetime import timedelta
        
        now = datetime.now()
        ttl_delta = timedelta(hours=self.session_ttl_hours)
        stale_sessions = []
        
        for session_id, last_access in self._session_last_access.items():
            if now - last_access > ttl_delta:
                stale_sessions.append(session_id)
        
        for session_id in stale_sessions:
            if session_id in self._sessions:
                del self._sessions[session_id]
            if session_id in self._session_last_access:
                del self._session_last_access[session_id]
        
        if stale_sessions:
            print(f"[MEMORY] Cleaned up {len(stale_sessions)} stale sessions (TTL: {self.session_ttl_hours}h)")
        
        return len(stale_sessions)
    
    def _evict_oldest_session(self) -> Optional[str]:
        """
        Evict the oldest (least recently accessed) session.
        Called when max_sessions limit is reached. Thread-safe (assumes lock is held).
        
        Returns:
            The session_id that was evicted, or None if no sessions to evict
        """
        if not self._session_last_access:
            return None
        
        # Find oldest session
        oldest_session = min(self._session_last_access.items(), key=lambda x: x[1])
        session_id = oldest_session[0]
        
        # Remove it
        if session_id in self._sessions:
            del self._sessions[session_id]
        if session_id in self._session_last_access:
            del self._session_last_access[session_id]
        
        print(f"[MEMORY] Evicted oldest session {session_id} (max_sessions: {self.max_sessions})")
        return session_id
    
    def get_memory_stats(self) -> Dict:
        """
        Get memory usage statistics.
        
        Returns:
            Dict with memory statistics
        """
        with self._lock:
            total_turns = sum(len(history) for history in self._sessions.values())
            avg_turns = total_turns / len(self._sessions) if self._sessions else 0
            
            return {
                "active_sessions": len(self._sessions),
                "max_sessions": self.max_sessions,
                "total_turns": total_turns,
                "avg_turns_per_session": round(avg_turns, 2),
                "max_history_length": self.max_history_length,
                "session_ttl_hours": self.session_ttl_hours
            }
    
    def clear_session(self, session_id: str) -> None:
        """
        Clear conversation history for a session.
        
        Args:
            session_id: Unique identifier for the session
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
            if session_id in self._session_last_access:
                del self._session_last_access[session_id]
    
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


# Global memory manager instance with safeguards
# - Max 50 turns per session (auto-trim)
# - Max 1000 concurrent sessions (auto-evict oldest)
# - 24-hour TTL for inactive sessions (auto-cleanup)
memory_manager = MemoryManager(max_history_length=50, max_sessions=1000, session_ttl_hours=24)