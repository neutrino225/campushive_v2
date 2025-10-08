# CampusHive API Testing Guide

This guide explains how to test the CampusHive API using the updated Postman collection, with a focus on the new memory management and session-based conversation features.

## Collection Overview

The Postman collection is organized into the following groups:

1. **Root & Health** - Basic health checks and system status
2. **Multi-Agent** - Core chat functionality with and without sessions
3. **Memory Management** - Memory-related operations
4. **Session-Based Conversations** - Complete conversation flow examples
5. **Admin - Vector Stores** - Administrative functions

## Prerequisites

1. **Start the CampusHive server**:

   ```bash
   cd /home/neutrino/projects/fyp_test
   python -m app.main
   ```

2. **Import the collection**: Import `postman/CampusHive_API.postman_collection.json` into Postman

3. **Set environment variables**:
   - `base_url`: Default is `http://localhost:8000`
   - `session_id`: Will be auto-generated or you can set manually

## Testing Scenarios

### 1. Basic Chat (No Memory)

Test the basic chat functionality without session memory:

**Requests to try:**

- `Multi-Agent > Chat (Non-Streaming)`: Simple question without context
- `Multi-Agent > Chat (Streaming)`: Same but with streaming response

**Expected behavior:** Each request is independent, no conversation context is maintained.

### 2. Session-Based Conversations

Test the complete conversation memory functionality:

**Step-by-step workflow:**

1. **Start New Conversation**

   - Run: `Session-Based Conversations > Start New Conversation`
   - This asks: "What is the email address of Dr. Akhtar Jamil?"
   - A session_id is automatically generated and stored
   - Response should contain the email address

2. **Follow-up Question 1**

   - Run: `Session-Based Conversations > Follow-up Question 1`
   - This asks: "Can you list his publications?"
   - Uses the same session_id from step 1
   - Should recognize "his" refers to Dr. Akhtar Jamil from context

3. **Follow-up Question 2**

   - Run: `Session-Based Conversations > Follow-up Question 2`
   - This asks: "Provide a summary about him"
   - Still maintains context about Dr. Akhtar Jamil

4. **View Conversation History**

   - Run: `Session-Based Conversations > View Conversation History`
   - Shows the complete conversation history for the session

5. **Clear Conversation**
   - Run: `Session-Based Conversations > Clear Conversation`
   - Clears the session memory

### 3. Memory Management Operations

Test memory management directly:

**Available operations:**

- `Memory Management > Get Session History`: View history for a specific session
- `Memory Management > Clear Session History`: Clear history for a specific session
- `Memory Management > Get Memory Statistics`: View overall memory stats

### 4. Multiple Session Testing

To test session isolation:

1. **Create Session A**:

   - Set `session_id` to "session_a"
   - Run chat requests about faculty

2. **Create Session B**:

   - Set `session_id` to "session_b"
   - Run chat requests about degrees

3. **Verify Isolation**:
   - Check history for each session separately
   - Ensure contexts don't bleed between sessions

## Key Test Cases

### Context Maintenance

```
User: "What is the email address of Dr. Akhtar Jamil?"
Bot: "akhtar.jamil@nu.edu.pk"

User: "Can you list his publications?"
Bot: [Should list Dr. Jamil's publications without asking who]

User: "What about his research interests?"
Bot: [Should still know we're talking about Dr. Jamil]
```

### Session Isolation

```
Session A: Ask about "Dr. Jamil"
Session B: Ask about "Dr. Smith"
Session A: Follow-up should still be about Dr. Jamil
Session B: Follow-up should still be about Dr. Smith
```

### Memory Limits

```
Session: Ask 15+ questions in sequence
Verify: Only last 10 conversations are kept (configurable)
```

## Response Formats

### Chat Response (Non-Streaming)

```json
{
	"response": "akhtar.jamil@nu.edu.pk",
	"route": ["faculty_agent"],
	"session_id": "demo_session_001"
}
```

### Chat Response (Streaming)

Server-sent events format:

```
data: {"event": "step", "node": "router", "session_id": "demo_session_001"}

data: {"response": "akhtar.jamil@nu.edu.pk", "route": ["faculty_agent"], "session_id": "demo_session_001"}
```

### Memory History Response

```json
{
	"session_id": "demo_session_001",
	"history": [
		{
			"user_message": "What is the email address of Dr. Akhtar Jamil?",
			"agent_response": "akhtar.jamil@nu.edu.pk",
			"timestamp": "2025-10-03T19:48:44.417192",
			"route": ["faculty_agent"]
		}
	]
}
```

### Memory Statistics Response

```json
{
	"active_sessions": 3,
	"session_ids": ["session_a", "session_b", "demo_session_001"]
}
```

## Common Issues & Troubleshooting

### Issue: Context Not Maintained

**Symptoms**: Follow-up questions don't maintain context
**Solutions**:

- Verify same `session_id` is used across requests
- Check that memory endpoints show conversation history
- Confirm server has memory management enabled

### Issue: Session Isolation Problems

**Symptoms**: Conversations bleed between sessions
**Solutions**:

- Use distinct `session_id` values
- Clear sessions between tests
- Check memory statistics to verify session separation

### Issue: Memory Growth

**Symptoms**: Memory usage increases over time
**Solutions**:

- Verify memory limits are configured (default: 10 turns)
- Clear old sessions periodically
- Check memory statistics for active session count

## Automated Testing Scripts

### Postman Test Scripts

Add to request "Tests" tab for automated validation:

```javascript
// Test for successful response
pm.test("Status code is 200", function () {
	pm.response.to.have.status(200);
});

// Test for response structure
pm.test("Response has required fields", function () {
	const response = pm.response.json();
	pm.expect(response).to.have.property("response");
	pm.expect(response).to.have.property("route");
	pm.expect(response).to.have.property("session_id");
});

// Store session_id for subsequent requests
if (pm.response.json().session_id) {
	pm.collectionVariables.set("session_id", pm.response.json().session_id);
}
```

### Collection Runner

For comprehensive testing:

1. Use Postman's Collection Runner
2. Run "Session-Based Conversations" folder in sequence
3. Verify each request builds on the previous context
4. Check memory operations work correctly

## Performance Testing

### Load Testing Considerations

- Multiple concurrent sessions
- Memory usage under load
- Response time with conversation history
- Session cleanup performance

### Monitoring Points

- Active session count
- Memory usage per session
- Average response time with context
- Context accuracy over long conversations

This testing approach ensures the memory system works correctly across all use cases while maintaining good performance and proper session isolation.
