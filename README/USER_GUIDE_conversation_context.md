# Conversation Context Feature - User Guide

## Overview

CampusHive now remembers your entire conversation history! When you switch between chats or return to a previous conversation, the AI will have full context of everything that was discussed before.

## How to Use

### Starting a New Conversation

1. Click the "New Chat" button in the sidebar
2. Type your first question
3. The AI responds with relevant information

### Continuing a Previous Conversation

1. **Select a previous chat** from the sidebar

   - All your past messages will load
   - The chat will appear in the main area

2. **Ask a follow-up question**

   - You can reference previous topics naturally
   - Use phrases like "tell me more about that" or "what about the first one"
   - The AI remembers everything from earlier in the conversation

3. **Get contextually aware responses**
   - The AI will understand what you're referring to
   - No need to repeat information from earlier messages

## Example Conversation

### Initial Question

**You**: What clubs are available on campus?

**CampusHive**: We have several clubs including:

- Programming Club
- Debate Club
- Sports Clubs
- Drama Club

### Follow-up Question (with context!)

**You**: Tell me more about the first one

**CampusHive**: The Programming Club meets every Tuesday at 6 PM in Room 301. They work on coding projects, participate in hackathons, and organize workshops on various programming topics.

_Notice: The AI understood "the first one" refers to Programming Club from your earlier message!_

### Another Follow-up

**You**: What time does it meet?

**CampusHive**: The Programming Club meets every Tuesday at 6 PM.

_The AI remembers you're asking about Programming Club without you having to specify!_

## Features

### ✅ What Works

- **Full conversation history**: All previous messages are remembered
- **Natural follow-ups**: Reference earlier topics without repeating yourself
- **Persistent across sessions**: Close and reopen - your context is still there
- **Multi-session support**: Each chat has its own independent context
- **Automatic**: No setup required - it just works!

### 📝 Tips for Best Results

1. **Be specific in your first question** to establish clear context
2. **Use natural language** - talk like you would with a human
3. **Reference previous topics** using phrases like:

   - "What about..."
   - "Tell me more about that"
   - "The one you mentioned earlier"
   - "Can you explain it in more detail?"

4. **Switch chats anytime** - your context is preserved in each conversation

## Technical Details (For Curious Users)

### How It Works

1. Every message you send is saved to the database
2. When you ask a new question, the AI loads all previous messages from that chat
3. The AI uses this history to understand your follow-up questions
4. Your new message and the AI's response are added to the history

### Privacy & Data

- Your conversations are stored securely in the database
- Each user's chats are completely separate and private
- Only you can see your conversation history
- Context is only shared within the same chat session

### Limitations

- History is limited to **10 conversation turns** (20 messages) to maintain performance
- Very old messages may be summarized or removed
- Context is session-specific (doesn't carry across different chats)

## Troubleshooting

### The AI doesn't remember my previous message

**Possible causes**:

- You switched to a different chat (each chat has separate context)
- The conversation is very long (older messages may be trimmed)
- There was an error loading the history

**Solution**:

- Make sure you're in the same chat session
- Try rephrasing your question with more context
- Check the browser console for errors (F12)

### I want to start fresh

**Solution**: Click "New Chat" to start a completely new conversation without any previous context.

## Support

If you encounter any issues with conversation context:

1. Check that you're logged in (required for saving history)
2. Verify you're in the correct chat session
3. Try refreshing the page
4. Contact support if problems persist

---

**Enjoy smarter, more natural conversations with CampusHive! 🎓**

# CampusHive Frontend Integration Guide: Auth, Chat Sessions, History, and SSE Streaming

This guide explains how to set up the CampusHive frontend for a secure, persistent, and real-time chat experience, including user authentication, chat session management, history loading, and Server-Sent Events (SSE) streaming from the backend.

---

## 1. User Authentication (JWT-based)

### Signup & Login

- Users must sign up or log in to access chat features.
- On successful login/signup, the backend returns a JWT token.
- Store the JWT token in `localStorage` (e.g., under `campushive_token`).

```js
function setToken(token) {
	if (token) localStorage.setItem("campushive_token", token);
	else localStorage.removeItem("campushive_token");
}
function getToken() {
	return localStorage.getItem("campushive_token");
}
```

### Authenticated Requests

- All API requests must include the JWT in the `Authorization` header:

```js
function authHeaders() {
	const t = getToken();
	return t
		? { Authorization: "Bearer " + t, "Content-Type": "application/json" }
		: { "Content-Type": "application/json" };
}
```

- On page load, check token validity by calling `/auth/me`. If invalid, show the login/signup modal.

---

## 2. Chat Session Management

### Creating a New Chat Session

- Use the `/chats` POST endpoint with a session name.
- Store the returned session ID and name in a local map for quick access.

```js
async function createSession(name) {
	const r = await fetch("/chats", {
		method: "POST",
		headers: authHeaders(),
		body: JSON.stringify({ session_name: name }),
	});
	const data = await r.json();
	// Store session info in sessionMap
}
```

### Listing and Selecting Sessions

- Fetch all sessions with `/chats` (GET).
- Display in a sidebar; clicking a session loads its messages and sets it as `currentSession`.

```js
function selectSession(session_name, id) {
	currentSession = { session_name, id };
	loadSessionMessages(id);
}
```

### Loading Session Messages

- Fetch messages for a session with `/chats/{id}`.
- Render all messages in the UI.

---

## 3. Chat History and Context

- When a session is selected, all previous messages are loaded and displayed.
- When sending a new message, always include the `session_id` so the backend can load and use the full conversation context.
- The backend will automatically load history from the database and populate the memory manager for the LLM.

---

## 4. Sending Messages & SSE Streaming Integration

### Submitting a Message

- On form submit, send a POST request to `/multiagent/chat` with:
  - `question`: the user's message
  - `session_id`: the current session's name
  - `stream: true`: to enable SSE streaming

```js
const response = await fetch("/multiagent/chat", {
	method: "POST",
	headers: authHeaders(),
	body: JSON.stringify({
		question,
		session_id: currentSession ? currentSession.session_name : null,
		stream: true,
	}),
});
```

### Handling SSE Streaming

- Use the `ReadableStream` API to process the SSE stream from the backend.
- Parse each chunk for `data:` lines, and update the UI in real time.

```js
const reader = response.body.getReader();
let partial = "";
while (true) {
	const { value, done } = await reader.read();
	if (done) break;
	const chunk = new TextDecoder().decode(value);
	// Parse SSE data lines
	const dataLines = chunk
		.split("\n")
		.filter((l) => l.trim().startsWith("data:"));
	for (const line of dataLines) {
		const payload = JSON.parse(line.replace(/^data:\s*/, ""));
		if (payload.response !== undefined) {
			partial = mergePartial(partial, payload.response);
			updateMarkdownBubble(bot.bubble, partial);
		}
		// Handle errors, steps, etc. as needed
	}
}
```

- `mergePartial` is a helper to combine partial responses for smooth streaming.
- `updateMarkdownBubble` renders markdown and updates the chat bubble in real time.

---

## 5. Best Practices & UX

- Always check for a valid JWT before making API calls.
- Show a loading indicator while waiting for SSE responses.
- Disable the send button during streaming to prevent duplicate sends.
- On session switch, clear the message area and load the selected session's history.
- Use `localStorage` to persist the last selected session if desired.

---

## 6. Example: Minimal End-to-End Flow

```js
// On page load
if (!getToken()) showAuthModal();
else loadUserInfo();

// On login/signup success
setToken(token);
loadUserInfo();

// On new chat
await createSession("Chat " + new Date().toLocaleString());

// On session select
selectSession(session_name, id);

// On message send
await handleSubmit(); // which streams response and updates UI
```

---

## 7. Troubleshooting

- If SSE streaming fails, check for:
  - Missing or invalid JWT (401/403 errors)
  - Network issues or CORS misconfiguration
  - Backend errors (check server logs)
- If chat history is missing, ensure the correct `session_id` is sent and the backend DB is persisting messages.

---

## 8. Security Notes

- JWT tokens should be stored securely (preferably in `httpOnly` cookies for production, but `localStorage` is acceptable for prototypes).
- Always use HTTPS in production to protect tokens in transit.
- Never expose sensitive user data in the frontend.

---

## 9. References

- [MDN: Using Fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
- [MDN: Server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)

---

With this setup, your CampusHive frontend will provide a secure, persistent, and real-time chat experience with full context and seamless session management.
