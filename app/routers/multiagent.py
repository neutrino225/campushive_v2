import os
import sys
import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

# Import application dependencies (auth + db models)
from app.auth import get_current_user
from app.database import get_db, ChatSession, ChatMessage, User

# Add root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

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

    def get_session_id_str(self) -> str:
        """Convert session_id to string for internal use."""
        if isinstance(self.session_id, int):
            return str(self.session_id)
        return self.session_id


async def load_history_into_memory(session_id: str, user_id: int, db: Session) -> None:
    """
    Load conversation history from database into memory manager.
    This ensures the LLM has context from previous messages.
    """
    from multiagent.memory import memory_manager

    def _load_sync(db, user_id, external_session_id):
        # Find the session by immutable DB id if numeric; otherwise by name (legacy)
        session = None
        if isinstance(external_session_id, str) and external_session_id.isdigit():
            session = (
                db.query(ChatSession)
                .filter(
                    ChatSession.id == int(external_session_id),
                    ChatSession.user_id == user_id,
                )
                .first()
            )
        if session is None:
            session = (
                db.query(ChatSession)
                .filter(
                    ChatSession.session_name == external_session_id,
                    ChatSession.user_id == user_id,
                )
                .first()
            )

        if not session:
            return []

        # Get all messages for this session, ordered by creation time
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )

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
    history = await asyncio.to_thread(_load_sync, db, user_id, session_id)

    # Check if memory already has this history loaded
    current_memory = memory_manager.get_history(session_id)
    if len(current_memory) == len(history):
        # Already loaded, skip
        return

    # Clear and reload
    memory_manager.clear_session(session_id)
    for user_msg, agent_msg, route in history:
        memory_manager.add_turn(session_id, user_msg, agent_msg, route)


async def stream_supervisor_response(
    question: str,
    session_id: str = "default",
    current_user: User | None = None,
    db: Session | None = None,
) -> AsyncGenerator[str, None]:
    """
    Streams the response from the supervisor graph, yielding intermediate steps and the final result.
    """
    from multiagent.memory import memory_manager

    # Load conversation history from database into memory if we have DB access
    if db is not None and current_user is not None:
        await load_history_into_memory(session_id, current_user.id, db)

    final_state = {}
    final_response = ""

    try:
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"[MultiAgent] stream_supervisor_response: user_id={getattr(current_user, 'id', None)}, session_id={session_id}"
        )
        try:
            if current_user is not None and session_id is not None:
                from multiagent.memory.retriever_manager import (
                    get_session_retriever_manager,
                )

                mgr = get_session_retriever_manager()
                logger.info(
                    f"[MultiAgent] Expected store path: {mgr.get_session_store_path(current_user.id, str(session_id))}"
                )
        except Exception:
            logger.exception("[MultiAgent] Failed to compute expected store path")
        # Initialize state with session information (include user_id to enable session-scoped tools)
        initial_state = {
            "question": question,
            "session_id": session_id,
            "user_id": (
                current_user.id if current_user is not None else None
            ),  # Ensure user_id is present
            "user_role": (current_user.role if current_user is not None else "student"),
            "route": [],
            "result": "",
            "conversation_history": [],
        }

        # Use the supervisor_graph.astream_events for more granular streaming
        async for event in supervisor_graph.astream_events(initial_state, version="v1"):
            kind = event["event"]
            if kind == "on_chain_end":
                # The final answer is in the `on_chain_end` event
                # for the 'student' or 'faculty' nodes
                node_name = event["name"]
                if node_name in ["student", "faculty", "direct", "exam"]:
                    data = event["data"].get("output")
                    if data and "result" in data:
                        final_state.update(data)
                        final_response = data["result"]
                        response_data = {
                            "response": data["result"],
                            "route": data.get("route", []),
                            "session_id": session_id,
                        }
                        yield f"data: {json.dumps(response_data)}\n\n"
            elif kind == "on_chain_stream":
                # Stream partial results
                node_name = event["name"]
                if node_name in ["student", "faculty", "direct", "exam"]:
                    data = event["data"].get("chunk")
                    if data and "result" in data:
                        response_data = {
                            "response": data["result"],
                            "route": data.get("route", []),
                            "session_id": session_id,
                        }
                        yield f"data: {json.dumps(response_data)}\n\n"
            elif kind == "on_chain_start":
                # Yield intermediate steps
                node_name = event["name"]
                if node_name in ["student", "faculty", "direct", "exam", "router"]:
                    yield f"data: {json.dumps({'event': 'step', 'node': node_name, 'session_id': session_id})}\n\n"

            await asyncio.sleep(0.01)  # Prevent blocking

        # Store the conversation turn in memory after streaming is complete
        if final_response:
            route = final_state.get("route", [])
            memory_manager.add_turn(session_id, question, final_response, route)

            # Persist to DB if we have a DB session and an authenticated user
            if db is not None and current_user is not None:
                # Use a sync helper in a thread to avoid blocking event loop
                def _persist_sync(
                    db,
                    user_id,
                    external_session_id,
                    user_message,
                    agent_response,
                    route,
                ):
                    # Find session by DB id when provided; otherwise fallback by name (legacy)
                    session = None
                    if (
                        isinstance(external_session_id, str)
                        and external_session_id.isdigit()
                    ):
                        session = (
                            db.query(ChatSession)
                            .filter(
                                ChatSession.id == int(external_session_id),
                                ChatSession.user_id == user_id,
                            )
                            .first()
                        )
                    if session is None:
                        session = (
                            db.query(ChatSession)
                            .filter(
                                ChatSession.session_name == external_session_id,
                                ChatSession.user_id == user_id,
                            )
                            .first()
                        )
                    if session is None:
                        # As a safety net, create a session with a safe default name rather than numeric id
                        session = ChatSession(user_id=user_id, session_name="New Chat")
                        db.add(session)
                        db.commit()
                        db.refresh(session)

                    # Persist the user message
                    user_msg = ChatMessage(
                        session_id=session.id,
                        message_type="user",
                        content=user_message,
                        agent_type=None,
                        message_metadata=None,
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
                        message_metadata=(
                            json.dumps({"route": route}) if route is not None else None
                        ),
                    )
                    db.add(agent_msg)

                    # update session timestamp
                    try:
                        session.updated_at = func.now()
                    except Exception:
                        pass

                    # If this is the very first turn (<= 2 messages after insert), we can compute a display title
                    db.commit()
                    msg_count = (
                        db.query(func.count(ChatMessage.id))
                        .filter(ChatMessage.session_id == session.id)
                        .scalar()
                        or 0
                    )
                    title = None
                    if msg_count <= 2:
                        # Summarize from this first user/agent pair
                        user_text = user_message
                        agent_text = agent_response
                        # Lightweight summarizer mirroring chats.py helper
                        source = (user_text or agent_text or "").strip()
                        source = " ".join(source.split())
                        lower = source.lower()
                        for p in [
                            "please",
                            "can you",
                            "could you",
                            "i want",
                            "i need",
                            "how do i",
                            "how to",
                            "what is",
                            "tell me",
                            "help me",
                        ]:
                            if lower.startswith(p + " "):
                                source = source[len(p) + 1 :]
                                break
                        cut_points = ["?", ".", "!"]
                        cut_idx = min(
                            [source.find(c) for c in cut_points if c in source]
                            or [len(source)]
                        )
                        snippet = source[:cut_idx]
                        words = snippet.split()
                        if len(words) > 10:
                            words = words[:10]
                        title = (" ".join(words) or source[:50]).strip()
                        if title:
                            title = title[:1].upper() + title[1:]
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
        fallback_message = (
            "I'm sorry, I couldn't process your question. Please try rephrasing it."
        )
        yield f"data: {json.dumps({'response': fallback_message, 'route': final_state.get('route', [])})}\n\n"


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Handles chat requests, supporting both streaming and non-streaming responses.
    """
    question = request.question
    session_id = request.get_session_id_str()

    # If session_id is a numeric string (from integer), verify user owns the session
    if isinstance(request.session_id, int) or (
        isinstance(request.session_id, str) and request.session_id.isdigit()
    ):
        try:
            session_id_int = int(request.session_id)
            # Verify the session exists and belongs to the user
            session = (
                db.query(ChatSession)
                .filter(
                    ChatSession.id == session_id_int,
                    ChatSession.user_id == current_user.id,
                )
                .first()
            )
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat session not found or access denied",
                )
            # CRITICAL FIX: Use immutable session.id instead of mutable session_name
            # session_name changes after auto-titling, breaking vector store lookup
            session_id = str(session.id)
        except ValueError:
            pass  # Not a valid integer, treat as regular string session_id

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if request.stream:
        # Use StreamingResponse for real-time updates
        return StreamingResponse(
            stream_supervisor_response(
                question, session_id, current_user=current_user, db=db
            ),
            media_type="text/event-stream",
        )
    else:
        # For non-streaming, run the supervisor and return the final result
        try:
            # Use the async version directly
            from multiagent.graph.supervisor import run_supervisor_async

            result = await run_supervisor_async(
                question,
                session_id,
                user_role=(
                    current_user.role if current_user is not None else "student"
                ),
                user_id=(current_user.id if current_user is not None else None),
            )

            # Persist result to DB (create/find session and store both user and agent messages)
            try:
                if db is not None and current_user is not None:

                    def _persist_sync(
                        db,
                        user_id,
                        external_session_id,
                        user_message,
                        agent_response,
                        route,
                    ):
                        session = (
                            db.query(ChatSession)
                            .filter(
                                ChatSession.session_name == external_session_id,
                                ChatSession.user_id == user_id,
                            )
                            .first()
                        )
                        if not session:
                            session = ChatSession(
                                user_id=user_id, session_name=external_session_id
                            )
                            db.add(session)
                            db.commit()
                            db.refresh(session)

                        user_msg = ChatMessage(
                            session_id=session.id,
                            message_type="user",
                            content=user_message,
                            agent_type=None,
                            message_metadata=None,
                        )
                        db.add(user_msg)
                        db.commit()
                        db.refresh(user_msg)

                        agent_msg = ChatMessage(
                            session_id=session.id,
                            message_type="agent",
                            content=agent_response,
                            agent_type="supervisor",
                            message_metadata=(
                                json.dumps({"route": result.get("route", [])})
                                if result is not None
                                else None
                            ),
                        )
                        db.add(agent_msg)
                        try:
                            session.updated_at = func.now()
                        except Exception:
                            pass
                        db.commit()

                        # Title generation for first turn
                        msg_count = (
                            db.query(func.count(ChatMessage.id))
                            .filter(ChatMessage.session_id == session.id)
                            .scalar()
                            or 0
                        )
                        title = None
                        if msg_count <= 2:
                            source = (user_message or agent_response or "").strip()
                            source = " ".join(source.split())
                            lower = source.lower()
                            for p in [
                                "please",
                                "can you",
                                "could you",
                                "i want",
                                "i need",
                                "how do i",
                                "how to",
                                "what is",
                                "tell me",
                                "help me",
                            ]:
                                if lower.startswith(p + " "):
                                    source = source[len(p) + 1 :]
                                    break
                            cut_points = ["?", ".", "!"]
                            cut_idx = min(
                                [source.find(c) for c in cut_points if c in source]
                                or [len(source)]
                            )
                            snippet = source[:cut_idx]
                            words = snippet.split()
                            if len(words) > 10:
                                words = words[:10]
                            title = (" ".join(words) or source[:50]).strip()
                            if title:
                                title = title[:1].upper() + title[1:]
                        return session.id, title

                    _sid, auto_title = await asyncio.to_thread(
                        _persist_sync,
                        db,
                        current_user.id,
                        session_id,
                        question,
                        result.get("result", ""),
                        result.get("route", []),
                    )
            except Exception:
                # Log persistence error but don't fail the request
                import logging

                logging.getLogger(__name__).exception(
                    "Failed to persist multiagent chat turn"
                )

            # Include a computed title if available (useful for UIs on non-streaming mode)
            if "title" not in result:
                if "route" in result:
                    pass  # keep original result untouched
            return {
                **result,
                "session_id": session_id,
                **({"title": auto_title} if locals().get("auto_title") else {}),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error processing question: {str(e)}"
            )


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
                "route": turn.route,
            }
            for turn in history
        ],
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
        "session_ids": memory_manager.get_all_sessions(),
    }


@router.get("/download-timetable/{filename}")
async def download_timetable(
    filename: str,
):
    """
    Download exported timetable files (CSV or Excel).

    Args:
        filename: The filename to download (e.g., 'timetable_20251016_143022.csv')
        current_user: Authenticated user (required)

    Returns:
        FileResponse with the requested file

    Raises:
        HTTPException 404: File not found
        HTTPException 403: Invalid file type or path traversal attempt
    """
    import os
    from pathlib import Path

    # Security: Validate filename to prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid filename"
        )

    # Only allow CSV and Excel files
    allowed_extensions = {".csv", ".xlsx"}
    file_ext = Path(filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only CSV and Excel files can be downloaded",
        )

    # Construct the full file path
    export_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "timetable_exports"
    )
    file_path = os.path.join(export_dir, filename)

    # Check if file exists
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    # Determine media type
    media_type = (
        "text/csv"
        if file_ext == ".csv"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Return the file for download
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
