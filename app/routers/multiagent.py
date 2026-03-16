import os
import sys
import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

# Import application dependencies (auth + db models)
from app.auth import get_current_user
from app.database import get_db, ChatSession, ChatMessage, User
from app.utils.titles import generate_chat_title

# Add root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from multiagent.graph.supervisor import run_supervisor, supervisor_graph

# Create an APIRouter
router = APIRouter(
    prefix="/multiagent",
    tags=["Multi-Agent"],
)

# Pydantic model for chat requests
class ChatRequest(BaseModel):
    question: str
    session_id: str | int = "default"  # Can be string or int (DB session ID)
    stream: bool = True
    user_input_mode: bool = False  # Set to True when resuming after awaiting_user_input
    
    def get_session_id_str(self) -> str:
        """Convert session_id to string for internal use."""
        if isinstance(self.session_id, int):
            return str(self.session_id)
        return self.session_id

def _build_internal_session_key(session_id: int | str) -> str:
    return f"chat_session:{session_id}"


def _resolve_chat_session(
    db: Session,
    user_id: int,
    db_session_id: int | None = None,
    external_session_id: str | None = None,
):
    query = db.query(ChatSession).filter(ChatSession.user_id == user_id)
    if db_session_id is not None:
        return query.filter(ChatSession.id == db_session_id).first()
    if external_session_id is not None:
        return query.filter(ChatSession.session_name == external_session_id).first()
    return None


async def load_history_into_memory(
    memory_session_id: str,
    user_id: int,
    db: Session,
    db_session_id: int | None = None,
    external_session_id: str | None = None,
) -> None:
    """
    Load conversation history from database into memory manager.
    This ensures the LLM has context from previous messages.
    """
    from multiagent.memory import memory_manager
    
    def _load_sync(db, user_id, db_session_id, external_session_id):
        session = _resolve_chat_session(
            db,
            user_id,
            db_session_id=db_session_id,
            external_session_id=external_session_id,
        )
        
        if not session:
            return []
        
        # Get all messages for this session, ordered by creation time
        messages = db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).order_by(ChatMessage.created_at.asc()).all()
        
        # Group messages into pairs (user + agent)
        history = []
        user_msg = None
        for msg in messages:
            if msg.message_type == "user":
                user_msg = msg
            elif msg.message_type == "agent" and user_msg:
                # Extract route from metadata
                route = []
                if msg.message_metadata:
                    try:
                        metadata = json.loads(msg.message_metadata)
                        route = metadata.get("route", [])
                    except:
                        pass
                history.append((user_msg.content, msg.content, route))
                user_msg = None
        
        return history
    
    # Load history from DB
    history = await asyncio.to_thread(
        _load_sync,
        db,
        user_id,
        db_session_id,
        external_session_id,
    )
    
    # Check if memory already has this history loaded
    current_memory = memory_manager.get_history(memory_session_id)
    if len(current_memory) == len(history):
        # Already loaded, skip
        return
    
    # Clear and reload
    memory_manager.clear_session(memory_session_id)
    for user_msg, agent_msg, route in history:
        memory_manager.add_turn(memory_session_id, user_msg, agent_msg, route)


async def stream_supervisor_response(
    question: str, 
    session_id: str = "default", 
    current_user: User | None = None, 
    db: Session | None = None,
    user_input_mode: bool = False,
    db_session_id: int | None = None,
) -> AsyncGenerator[str, None]:
    """
    Streams the response from the supervisor graph, yielding intermediate steps and the final result.
    For planning mode queries, may yield scratchpad steps and user input requests.
    """
    from multiagent.memory import memory_manager
    from multiagent.graph.supervisor import run_supervisor_async
    
    # Load conversation history from database into memory if we have DB access
    if db is not None and current_user is not None:
        await load_history_into_memory(
            session_id,
            current_user.id,
            db,
            db_session_id=db_session_id,
            external_session_id=None if db_session_id is not None else session_id,
        )
    
    final_state = {}
    final_response = ""
    
    try:
        # Use run_supervisor_async which handles planning mode internally
        user_role = (current_user.role if current_user is not None else "student")
        result = await run_supervisor_async(
            question, 
            session_id, 
            user_role=user_role,
            user_input_mode=user_input_mode
        )
        
        # Check if waiting for user input (planning mode)
        if result.get("awaiting_user_input"):
            # Yield scratchpad steps first
            for step in result.get("scratchpad", []):
                yield f"data: {json.dumps({'event': 'scratchpad', 'step': step, 'session_id': session_id})}\n\n"
            
            # Yield user input request
            yield f"data: {json.dumps({'event': 'user_input_request', 'question': result.get('response'), 'awaiting_user_input': True, 'planning_mode': True, 'route': result.get('route', []), 'session_id': session_id})}\n\n"
            
            # Don't persist yet - waiting for user response
            return
        
        # Regular response - yield it
        final_state = result
        # Some supervisor error paths return only `response` (without `result`).
        # Prefer `result`, then fall back to `response` so errors are surfaced to clients.
        final_response = result.get("result") or result.get("response", "")
        
        # Yield scratchpad if present (planning mode completed)
        if result.get("scratchpad"):
            for step in result.get("scratchpad", []):
                yield f"data: {json.dumps({'event': 'scratchpad', 'step': step, 'session_id': session_id})}\n\n"
        
        # Yield route steps
        for route_step in result.get("route", []):
            yield f"data: {json.dumps({'event': 'step', 'node': route_step, 'session_id': session_id})}\n\n"
        
        # Yield final response
        response_data = {
            "response": final_response,
            "route": result.get("route", []),
            "planning_mode": result.get("planning_mode", False),
            "session_id": session_id
        }
        yield f"data: {json.dumps(response_data)}\n\n"

        # Store the conversation turn in memory after streaming is complete
        if final_response:
            route = final_state.get("route", [])
            memory_manager.add_turn(session_id, question, final_response, route)

            # Persist to DB if we have a DB session and an authenticated user
            if db is not None and current_user is not None:
                # Use a sync helper in a thread to avoid blocking event loop
                def _persist_sync(db, user_id, external_session_id, user_message, agent_response, route):
                    session = _resolve_chat_session(
                        db,
                        user_id,
                        db_session_id=db_session_id,
                        external_session_id=external_session_id,
                    )
                    if not session:
                        session = ChatSession(user_id=user_id, session_name=external_session_id)
                        db.add(session)
                        db.commit()
                        db.refresh(session)

                    # Persist the user message
                    user_msg = ChatMessage(
                        session_id=session.id,
                        message_type="user",
                        content=user_message,
                        agent_type=None,
                        message_metadata=None
                    )
                    db.add(user_msg)
                    db.commit()
                    db.refresh(user_msg)

                    # Persist the agent response
                    agent_msg = ChatMessage(
                        session_id=session.id,
                        message_type="agent",
                        content=agent_response,
                        agent_type="supervisor",
                        message_metadata=json.dumps({"route": route}) if route is not None else None
                    )
                    db.add(agent_msg)

                    # update session timestamp
                    try:
                        session.updated_at = func.now()
                    except Exception:
                        pass

                    # If this is the very first turn (<= 2 messages after insert), we can compute a display title
                    db.commit()
                    msg_count = db.query(func.count(ChatMessage.id)).filter(ChatMessage.session_id == session.id).scalar() or 0
                    title = None
                    if msg_count <= 2:
                        title = generate_chat_title(user_message, agent_response)
                    return session.id, title

                session_row_id, auto_title = await asyncio.to_thread(
                    _persist_sync,
                    db,
                    current_user.id,
                    session_id,
                    question,
                    final_response,
                    route,
                )

                # Emit a synthetic SSE for front-end to optionally update its list item title
                if auto_title:
                    yield f"data: {json.dumps({'event': 'title', 'session_id': session_id, 'title': auto_title})}\n\n"

    except Exception as e:
        error_message = f"Error processing question: {str(e)}"
        yield f"data: {json.dumps({'error': error_message, 'session_id': session_id})}\n\n"

    if not final_state.get("result", "").strip():
        fallback_message = "I'm sorry, I couldn't process your question. Please try rephrasing it."
        yield f"data: {json.dumps({'response': fallback_message, 'route': final_state.get('route', [])})}\n\n"


@router.post("/chat")
async def chat_endpoint(request: ChatRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Handles chat requests, supporting both streaming and non-streaming responses.
    """
    question = request.question
    public_session_id = request.get_session_id_str()
    internal_session_id = public_session_id
    db_session_id: int | None = None
    
    # If session_id is a numeric string (from integer), verify user owns the session
    if isinstance(request.session_id, int) or (isinstance(request.session_id, str) and request.session_id.isdigit()):
        try:
            session_id_int = int(request.session_id)
            # Verify the session exists and belongs to the user
            session = db.query(ChatSession).filter(
                ChatSession.id == session_id_int,
                ChatSession.user_id == current_user.id
            ).first()
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat session not found or access denied"
                )
            db_session_id = session.id
            internal_session_id = _build_internal_session_key(session.id)
        except ValueError:
            pass  # Not a valid integer, treat as regular string session_id
    
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if request.stream:
        # Use StreamingResponse for real-time updates
        return StreamingResponse(
            stream_supervisor_response(
                question, 
                internal_session_id, 
                current_user=current_user, 
                db=db,
                user_input_mode=request.user_input_mode,
                db_session_id=db_session_id,
            ),
            media_type="text/event-stream",
        )
    else:
        # For non-streaming, run the supervisor and return the final result
        try:
            # Use the async version directly
            from multiagent.graph.supervisor import run_supervisor_async
            
            # Check if this is a user input resumption (not implemented yet, will add in next step)
            user_input_mode = request.user_input_mode if hasattr(request, 'user_input_mode') else False
            
            result = await run_supervisor_async(
                question, 
                internal_session_id, 
                user_role=(current_user.role if current_user is not None else "student"),
                user_input_mode=user_input_mode
            )

            # Check if planning mode is waiting for user input
            if result.get("awaiting_user_input"):
                # Don't persist to DB yet - waiting for user response
                # Return special response with scratchpad
                return {
                    "response": result.get("response"),
                    "awaiting_user_input": True,
                    "scratchpad": result.get("scratchpad", []),
                    "route": result.get("route", []),
                    "planning_mode": True,
                    "session_id": public_session_id
                }

            # Persist result to DB (create/find session and store both user and agent messages)
            try:
                if db is not None and current_user is not None:
                    def _persist_sync(db, user_id, external_session_id, user_message, agent_response, route):
                        session = _resolve_chat_session(
                            db,
                            user_id,
                            db_session_id=db_session_id,
                            external_session_id=external_session_id,
                        )
                        if not session:
                            session = ChatSession(user_id=user_id, session_name=external_session_id)
                            db.add(session)
                            db.commit()
                            db.refresh(session)

                        user_msg = ChatMessage(
                            session_id=session.id,
                            message_type="user",
                            content=user_message,
                            agent_type=None,
                            message_metadata=None
                        )
                        db.add(user_msg)
                        db.commit()
                        db.refresh(user_msg)

                        agent_msg = ChatMessage(
                            session_id=session.id,
                            message_type="agent",
                            content=agent_response,
                            agent_type="supervisor",
                            message_metadata=json.dumps({"route": result.get("route", [])}) if result is not None else None
                        )
                        db.add(agent_msg)
                        try:
                            session.updated_at = func.now()
                        except Exception:
                            pass
                        db.commit()

                        # Title generation for first turn
                        msg_count = db.query(func.count(ChatMessage.id)).filter(ChatMessage.session_id == session.id).scalar() or 0
                        title = None
                        if msg_count <= 2:
                            title = generate_chat_title(user_message, agent_response)
                        return session.id, title

                    _sid, auto_title = await asyncio.to_thread(
                        _persist_sync,
                        db,
                        current_user.id,
                        public_session_id,
                        question,
                        result.get("result", ""),
                        result.get("route", []),
                    )
            except Exception:
                # Log persistence error but don't fail the request
                import logging
                logging.getLogger(__name__).exception("Failed to persist multiagent chat turn")

            # Include a computed title if available (useful for UIs on non-streaming mode)
            if 'title' not in result:
                if 'route' in result:
                    pass  # keep original result untouched
            return {**result, "session_id": public_session_id, **({"title": auto_title} if locals().get("auto_title") else {})}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")


# Memory management endpoints
@router.get("/memory/{session_id}")
async def get_session_history(session_id: str):
    """Get conversation history for a session."""
    from multiagent.memory import memory_manager
    
    history = memory_manager.get_history(session_id)
    return {
        "session_id": session_id,
        "history": [
            {
                "user_message": turn.user_message,
                "agent_response": turn.agent_response,
                "timestamp": turn.timestamp.isoformat(),
                "route": turn.route
            }
            for turn in history
        ]
    }


@router.delete("/memory/{session_id}")
async def clear_session_history(session_id: str):
    """Clear conversation history for a session."""
    from multiagent.memory import memory_manager
    
    memory_manager.clear_session(session_id)
    return {"message": f"Session {session_id} history cleared"}


@router.get("/memory")
async def get_memory_stats():
    """Get memory statistics."""
    from multiagent.memory import memory_manager
    
    return {
        "active_sessions": memory_manager.get_session_count(),
        "session_ids": memory_manager.get_all_sessions()
    }
