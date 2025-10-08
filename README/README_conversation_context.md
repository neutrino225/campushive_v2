# Conversation Context Loading

## Overview

The CampusHive chatbot now supports full conversation context when users switch between chat sessions. This means the LLM can remember and reference previous messages in the conversation.

## How It Works

### Backend (Automatic)

When a user sends a message in a chat session, the backend automatically:

1. **Loads History from Database**:

   - Queries the database for all previous messages in the session
   - Retrieves user messages paired with agent responses
   - Extracts routing information from message metadata

2. **Populates Memory Manager**:

   - Clears any stale in-memory history for the session
   - Loads all conversation turns into the memory manager
   - Maintains chronological order of messages

3. **Provides Context to LLM**:
   - The supervisor graph has access to the memory manager
   - Previous context is available when generating responses
   - The LLM can reference earlier parts of the conversation

### Frontend (User Experience)

From the user's perspective:

1. **Switching Sessions**:

   - Click on any previous chat in the sidebar
   - All messages are loaded and displayed
   - The next question will have full conversation context

2. **Continuing Conversations**:

   - Ask follow-up questions naturally
   - Reference previous topics or answers
   - The LLM maintains context throughout the session

3. **Visual Feedback**:
   - Console logs confirm when a session is switched
   - Chat history loads immediately in the UI

## Implementation Details

### Database Schema

```
ChatSession
├── session_name (external identifier)
├── user_id (ownership)
└── messages (relationship)

ChatMessage
├── message_type ("user" or "agent")
├── content (message text)
├── agent_type (e.g., "supervisor")
└── message_metadata (JSON with route info)
```

### Memory Manager

- Stores conversation turns in memory: `(user_message, agent_response, route)`
- Thread-safe operations with RLock
- Maximum history length: 10 turns by default (configurable)
- Session-based isolation (each session has its own history)

### API Flow

```
1. Frontend sends: POST /multiagent/chat
   { question, session_id, stream: true }

2. Backend calls: load_history_into_memory()
   - Fetches from DB
   - Populates memory_manager

3. Supervisor graph executes:
   - Has access to memory_manager.get_history(session_id)
   - Can reference previous context

4. Response streams back to frontend
   - New turn is added to memory
   - New turn is persisted to DB
```

## Example Use Case

**User**: "What clubs are available on campus?"
**Bot**: "We have programming club, debate club, and sports clubs..."

_User switches to a different chat, then comes back_

**User**: "Tell me more about the first one"
**Bot**: "The programming club meets every Tuesday..."
_(The LLM remembers "the first one" refers to programming club)_

## Configuration

The history loading is automatic and requires no configuration. However, you can adjust:

- `max_history_length` in MemoryManager (default: 10 turns)
- Session timeout (currently no timeout - sessions persist indefinitely)

## Technical Notes

- History loading happens on every request (cached in memory after first load)
- Memory is cleared and reloaded only if DB history length differs from memory
- Thread-safe operations prevent race conditions in concurrent requests
- Async/await pattern used throughout to prevent blocking
