from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db, User
from app.auth.security import decode_access_token

# Security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    
    Args:
        credentials: HTTP Bearer credentials containing the JWT token
        db: Database session
    
    Returns:
        User object if authentication is successful
    
    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if payload is None:
        raise credentials_exception
    
    user_id: Optional[int] = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to ensure the current user is active.
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        User object if user is active
    
    Raises:
        HTTPException: If user is inactive
    """
    # For future use if we add an 'is_active' field
    return current_user


async def require_role(required_role: str):
    """
    Dependency factory to require a specific user role.
    
    Args:
        required_role: Role required to access the endpoint
    
    Returns:
        Dependency function that checks user role
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. {required_role.capitalize()} role required.",
            )
        return current_user
    return role_checker


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to require admin role.
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        User object if user is admin
    
    Raises:
        HTTPException: If user is not an admin
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin role required.",
        )
    return current_user
