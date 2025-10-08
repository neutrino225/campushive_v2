from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.database import get_db, User, ChatSession, ChatMessage
from app.schemas import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatSessionWithMessages,
    ChatMessageCreate,
    ChatMessageResponse,
)
from app.auth import get_current_user
import logging
import json

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
    new_session = ChatSession(
        user_id=current_user.id,
        session_name=session_data.session_name
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


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
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
    
    return None
