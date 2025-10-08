# Conversation Memory System

This document describes the conversation memory system implemented in CampusHive to enable context-aware multi-turn conversations.

## Overview

The memory system allows the agent to maintain conversation history per user session, enabling users to ask follow-up questions that reference previous context without needing to repeat information.

## Architecture

### Core Components

1. **MemoryManager** (`multiagent/memory/manager.py`)

   - Manages conversation history for multiple users/sessions
   - Thread-safe operations with proper locking
   - Configurable history length (default: 10 turns)
   - In-memory storage with optional persistent backend support

2. **ConversationTurn** (`multiagent/memory/manager.py`)

   - Data structure representing a single conversation turn
   - Contains user message, agent response, timestamp, and routing information
   - Serializable to/from JSON for persistence

3. **SupervisorState Enhancement** (`multiagent/graph/supervisor.py`)
   - Extended to include session_id and conversation_history
   - Context-aware routing based on conversation history
   - Automatic memory storage after each interaction

### Key Features

- **Session Isolation**: Each user/session has separate conversation history
- **Context-Aware Routing**: Router considers previous conversations for better intent classification
- **Automatic Memory Management**: Conversations are automatically stored after each interaction
- **Configurable History Length**: Prevents unbounded memory growth
- **Thread-Safe**: Supports concurrent access from multiple users
- **Export/Import**: Conversation history can be exported/imported as JSON

## Usage

### API Integration

The REST API now accepts an optional `session_id` parameter:

```json
{
	"question": "What is Dr. Jamil's email?",
	"session_id": "user_123",
	"stream": true
}
```

If no `session_id` is provided, it defaults to "default".

### CLI Integration

The CLI automatically generates a unique session ID per run and provides commands:

- `history` - Show conversation history
- `clear` - Clear current session history
- `exit`/`quit` - Exit the application

### Web Interface Integration

The web interface automatically generates and maintains a session ID in localStorage, providing seamless multi-turn conversations.

## Memory Management Endpoints

### Get Session History

```
GET /multiagent/memory/{session_id}
```

Returns the conversation history for a specific session.

### Clear Session History

```
DELETE /multiagent/memory/{session_id}
```

Clears the conversation history for a specific session.

### Get Memory Statistics

```
GET /multiagent/memory
```

Returns statistics about active sessions and memory usage.

## Example Conversation Flow

```
User: "What is the email address of Dr. Akhtar Jamil?"
Bot: "akhtar.jamil@nu.edu.pk"

User: "Can you list his publications?"
Bot: [Lists Dr. Jamil's publications - context maintained]

User: "Provide a summary about him"
Bot: [Provides summary about Dr. Jamil - still maintains context]
```

The system recognizes that follow-up questions refer to the same person without requiring the user to repeat the name.

## Context Enhancement

The system enhances questions with conversation context in two ways:

1. **Routing Enhancement**: The supervisor router gets enhanced questions with context hints for better classification
2. **Agent Context**: Individual agents receive recent conversation history to provide context-aware responses

## Configuration

The memory system can be configured by modifying the `MemoryManager` initialization:

```python
# In multiagent/memory/manager.py
memory_manager = MemoryManager(max_history_length=10)  # Adjust as needed
```

## Future Enhancements

- **Persistent Storage**: Add Redis/database backend for production deployments
- **Memory Summarization**: Implement conversation summarization for very long conversations
- **User Preferences**: Store long-term user preferences and context
- **Memory Analytics**: Add insights into conversation patterns and effectiveness

## Implementation Details

### Memory Storage

- **In-Memory**: Current implementation uses Python dictionaries with thread-safe access
- **Session-Based**: Each session maintains its own conversation history
- **Automatic Cleanup**: Sessions with no activity could be expired (future enhancement)

### Context Passing

- **Recent Context**: Last N conversation turns are passed to agents
- **Formatted Context**: History is formatted as a readable conversation log
- **Smart Truncation**: Long responses are truncated to prevent context overflow

### Thread Safety

- Uses `threading.RLock()` for thread-safe operations
- Supports concurrent access from multiple users/sessions
- No blocking operations in critical sections

## Testing

The memory system has been tested with:

- ✅ Basic conversation turn storage and retrieval
- ✅ Multi-session isolation
- ✅ Context-aware follow-up questions
- ✅ CLI integration with session commands
- ✅ Thread safety with concurrent access
- ✅ Memory management and cleanup
