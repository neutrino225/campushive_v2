from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db, User
from app.schemas import UserResponse, UserRoleUpdate
from app.auth import require_admin
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/users", tags=["User Management"])


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    List all users in the system.
    
    **Admin only endpoint.**
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    """
    users = db.query(User).offset(skip).limit(limit).all()
    logger.info(f"Admin {current_user.username} listed users (skip={skip}, limit={limit})")
    
    return [UserResponse.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get specific user information by ID.
    
    **Admin only endpoint.**
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse.model_validate(user)


@router.put("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    role_update: UserRoleUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Update a user's role.
    
    **Admin only endpoint.**
    
    - **role**: New role for the user (student, faculty, or admin)
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    old_role = user.role
    user.role = role_update.role
    
    db.commit()
    db.refresh(user)
    
    logger.info(
        f"Admin {current_user.username} changed role for user {user.username} "
        f"(ID: {user.id}) from {old_role} to {role_update.role}"
    )
    
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete a user account.
    
    **Admin only endpoint.**
    
    Warning: This will also delete all associated chat sessions and messages.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    username = user.username
    db.delete(user)
    db.commit()
    
    logger.warning(
        f"Admin {current_user.username} deleted user {username} (ID: {user_id})"
    )
    
    return None
