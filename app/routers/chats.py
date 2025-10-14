from fastapi import APIRouter, Depends, HTTPException, status
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
from app.utils.titles import generate_chat_title
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["Chat Management"])


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
        display_title = generate_chat_title(first_user, first_agent)

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
    display_title = generate_chat_title(first_user, first_agent)

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
    display_title = generate_chat_title(first_user, first_agent)
    
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
