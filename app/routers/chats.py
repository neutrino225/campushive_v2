from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.database import get_db, User, ChatSession, ChatMessage
from app.schemas import (
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatSessionResponse,
    ChatSessionWithMessages,
    ChatMessageCreate,
    ChatMessageResponse,
)
from app.auth import get_current_user
import logging
import json
import mimetypes
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["Chat Management"])


def _summarize_title(user_text: str | None, agent_text: str | None) -> str | None:
    """
    Create a compact, human-friendly title from the first user message
    (and optionally first agent reply). Keep it short like ChatGPT.
    """
    if not user_text and not agent_text:
        return None

    source = (user_text or "").strip()
    if not source and agent_text:
        source = agent_text.strip()

    # Use first sentence-ish; fall back to first 6-10 words
    # Remove newlines and extra spaces
    source = " ".join(source.split())
    # Strip common prefixes
    prefixes = ["please", "can you", "could you", "i want", "i need", "how do i", "how to", "what is", "tell me", "help me"]
    lower = source.lower()
    for p in prefixes:
        if lower.startswith(p + " "):
            source = source[len(p)+1:]
            break

    # Cut at sentence end or cap tokens
    cut_points = ["?", ".", "!"]
    cut_idx = min([source.find(c) for c in cut_points if c in source] or [len(source)])
    snippet = source[:cut_idx]
    words = snippet.split()
    if len(words) > 10:
        words = words[:10]
    title = " ".join(words).strip()
    if not title:
        title = (source[:50] + ("…" if len(source) > 50 else "")).strip()

    # Capitalize nicely
    title = title[:1].upper() + title[1:]
    return title


@router.get("", response_model=List[ChatSessionResponse])
async def list_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all chat sessions for the current user.
    
    Returns sessions ordered by most recently updated first.
    """
    sessions = (
        db.query(
            ChatSession,
            func.count(ChatMessage.id).label("message_count")
        )
        .outerjoin(ChatMessage, ChatSession.id == ChatMessage.session_id)
        .filter(ChatSession.user_id == current_user.id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    
    result = []
    for session, message_count in sessions:
        # Compute a display title from the first turn
        first_two = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.asc())
            .limit(2)
            .all()
        )
        first_user = next((m.content for m in first_two if m.message_type == "user"), None)
        first_agent = next((m.content for m in first_two if m.message_type != "user"), None)
        display_title = _summarize_title(first_user, first_agent)

        session_dict = {
            "id": session.id,
            "user_id": session.user_id,
            "session_name": session.session_name,
            "title": session.session_name,  # Add 'title' field for backwards compatibility
            "display_title": display_title,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "message_count": message_count
        }
        result.append(ChatSessionResponse(**session_dict))
    
    return result


@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    session_data: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new chat session.
    
    - **session_name**: Name for the chat session
    """
    safe_name = session_data.session_name or "New Chat"
    new_session = ChatSession(
        user_id=current_user.id,
        session_name=safe_name
    )
    
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    logger.info(
        f"User {current_user.username} created new chat session "
        f"'{new_session.session_name}' (ID: {new_session.id})"
    )
    
    return ChatSessionResponse(
        id=new_session.id,
        user_id=new_session.user_id,
        session_name=new_session.session_name,
        display_title=None,
        created_at=new_session.created_at,
        updated_at=new_session.updated_at,
        message_count=0
    )


@router.get("/sessions/{session_id}", response_model=ChatSessionWithMessages)
@router.get("/{session_id}", response_model=ChatSessionWithMessages)
async def get_chat_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific chat session with all its messages.
    
    Returns the session details and all messages in chronological order.
    """
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
    
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()
    
    # Compute display title from earliest turn
    first_two = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).limit(2).all()
    first_user = next((m.content for m in first_two if m.message_type == "user"), None)
    first_agent = next((m.content for m in first_two if m.message_type != "user"), None)
    display_title = _summarize_title(first_user, first_agent)

    return ChatSessionWithMessages(
        id=session.id,
        user_id=session.user_id,
        session_name=session.session_name,
        display_title=display_title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[ChatMessageResponse.model_validate(msg) for msg in messages]
    )


@router.post("/{session_id}/messages", response_model=ChatMessageResponse)
async def add_message_to_session(
    session_id: int,
    message_data: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a message to a chat session.
    
    This endpoint is for storing user messages. Agent responses should be 
    added through the multiagent endpoint which will store both user and agent messages.
    """
    # Verify session exists and belongs to current user
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
    
    # Create new message
    new_message = ChatMessage(
        session_id=session_id,
        message_type="user",
        content=message_data.content,
        agent_type=None,
        message_metadata=None
    )
    
    db.add(new_message)
    
    # Update session timestamp
    session.updated_at = func.now()
    
    db.commit()
    db.refresh(new_message)
    
    return ChatMessageResponse.model_validate(new_message)


@router.put("/{session_id}", response_model=ChatSessionResponse)
@router.patch("/{session_id}", response_model=ChatSessionResponse)
async def update_chat_session(
    session_id: int,
    session_data: ChatSessionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a chat session's name.
    
    Only the session owner can update the session.
    """
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
    
    # Update session name if provided
    if session_data.session_name is not None:
        session.session_name = session_data.session_name
    
    # Update timestamp
    session.updated_at = func.now()
    
    db.commit()
    db.refresh(session)
    
    # Get message count
    message_count = db.query(func.count(ChatMessage.id)).filter(
        ChatMessage.session_id == session_id
    ).scalar() or 0
    
    # Get display title
    first_two = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).limit(2).all()
    first_user = next((m.content for m in first_two if m.message_type == "user"), None)
    first_agent = next((m.content for m in first_two if m.message_type != "user"), None)
    display_title = _summarize_title(first_user, first_agent)
    
    logger.info(
        f"User {current_user.username} updated chat session "
        f"(ID: {session_id}) to '{session.session_name}'"
    )
    
    return ChatSessionResponse(
        id=session.id,
        user_id=session.user_id,
        session_name=session.session_name,
        title=session.session_name,
        display_title=display_title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=message_count
    )


@router.delete("/{session_id}", status_code=status.HTTP_200_OK)
async def delete_chat_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a chat session.
    
    This will also delete all associated messages.
    """
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
    
    session_name = session.session_name
    db.delete(session)
    db.commit()
    
    logger.info(
        f"User {current_user.username} deleted chat session "
        f"'{session_name}' (ID: {session_id})"
    )
    
    return {"status": "success", "message": "Chat session deleted"}


@router.post("/{session_id}/upload", status_code=status.HTTP_200_OK)
async def upload_document(
    session_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a document to a chat session for context-aware responses.
    
    Supported formats: .txt, .md, .pdf, .doc, .docx
    
    The document will be:
    1. Parsed to extract text
    2. Chunked into smaller pieces
    3. Embedded using the project's embedding model
    4. Stored in a session-specific vector store
    5. Made available to all agents for RAG operations
    """
    from multiagent.utils.document_parser import parse_document, is_supported_file
    from multiagent.memory.retriever_manager import get_session_retriever_manager
    
    # Verify session exists and belongs to user
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
    
    # Validate file type
    if not is_supported_file(file.filename):
        from multiagent.utils.document_parser import get_supported_extensions
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Supported formats: {', '.join(get_supported_extensions())}"
        )
    
    # File size limit (10 MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB in bytes
    file_size = 0
    
    # Check Content-Length header if available
    if hasattr(file, 'size') and file.size:
        file_size = file.size
    else:
        # Read file size by seeking to end
        try:
            file_content = await file.read()
            file_size = len(file_content)
            # Reset file pointer for later reading
            await file.seek(0)
        except Exception as e:
            logger.error(f"Error checking file size: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to check file size"
            )
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size allowed: {MAX_FILE_SIZE // (1024*1024)} MB"
        )
    
    # MIME type validation
    allowed_mime_types = {
        '.txt': ['text/plain'],
        '.md': ['text/plain', 'text/markdown'],
        '.pdf': ['application/pdf'],
        '.doc': ['application/msword'],
        '.docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    }
    
    # Get file extension
    _, ext = os.path.splitext(file.filename.lower())
    
    # Get MIME type from file content
    detected_mime = mimetypes.guess_type(file.filename)[0]
    
    # Also check Content-Type header if available
    content_type = getattr(file, 'content_type', None) or getattr(file, 'headers', {}).get('content-type')
    
    # Validate MIME type
    expected_mimes = allowed_mime_types.get(ext, [])
    if expected_mimes:
        mime_valid = False
        
        # Check detected MIME type
        if detected_mime and detected_mime in expected_mimes:
            mime_valid = True
        
        # Check Content-Type header
        if content_type and content_type in expected_mimes:
            mime_valid = True
        
        if not mime_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid MIME type for {ext} file. Expected: {', '.join(expected_mimes)}"
            )
    
    # Read file content for parsing
    try:
        # Reset file pointer to beginning (in case it was read before)
        await file.seek(0)
        file_content = await file.read()
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read file"
        )
    
    # Parse document to extract text
    try:
        text_content = parse_document(file_content, file.filename)
    except Exception as e:
        logger.error(f"Error parsing document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse document: {str(e)}"
        )
    
    # Ingest document into session-specific vector store
    try:
        manager = get_session_retriever_manager()
        # CRITICAL FIX: Use immutable session.id instead of mutable session_name
        # session_name changes after auto-titling, breaking vector store lookup
        result = manager.ingest_document(
            user_id=current_user.id,
            session_id=str(session.id),  # Use immutable DB ID for consistent path
            text_content=text_content,
            filename=file.filename
        )
        
        logger.info(
            f"User {current_user.username} uploaded '{file.filename}' "
            f"to session ID {session.id} (name: {session.session_name}) - {result['chunks_created']} chunks"
        )
        
        return {
            "status": "success",
            "message": "Document uploaded and processed successfully",
            "filename": file.filename,
            "chunks_created": result["chunks_created"]
        }
    
    except Exception as e:
        logger.error(f"Error ingesting document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(e)}"
        )
