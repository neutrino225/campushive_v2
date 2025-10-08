from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ChatMessageCreate(BaseModel):
    """Schema for creating a chat message."""
    content: str = Field(..., min_length=1)


class ChatMessageResponse(BaseModel):
    """Schema for chat message response."""
    id: int
    session_id: int
    message_type: str
    content: str
    agent_type: Optional[str] = None
    message_metadata: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class ChatSessionCreate(BaseModel):
    """Schema for creating a chat session."""
    session_name: str = Field(..., min_length=1, max_length=100)
    display_title: str | None = Field(default=None, max_length=150)


class ChatSessionResponse(BaseModel):
    """Schema for chat session response."""
    id: int
    user_id: int
    session_name: str
    display_title: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: Optional[int] = 0
    
    class Config:
        from_attributes = True


class ChatSessionWithMessages(BaseModel):
    """Schema for chat session with all messages."""
    id: int
    user_id: int
    session_name: str
    display_title: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessageResponse] = []
    
    class Config:
        from_attributes = True
