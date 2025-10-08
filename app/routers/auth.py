from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db, User
from app.schemas import UserSignup, UserLogin, TokenResponse, UserResponse
from app.auth import verify_password, get_password_hash, create_access_token, get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserSignup, db: Session = Depends(get_db)):
    """
    Register a new user account.
    
    - **username**: Unique username (3-50 characters, alphanumeric and underscore only)
    - **email**: Valid email address
    - **password**: Strong password (min 8 chars, must include uppercase, lowercase, and digit)
    
    Returns a JWT token and user information.
    """
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user with default 'student' role
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_password,
        role="student"  # Default role
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    logger.info(f"New user registered: {new_user.username} (ID: {new_user.id})")
    
    # Create access token
    access_token = create_access_token(data={"sub": str(new_user.id), "role": new_user.role})
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(new_user)
    )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Login with username and password.
    
    - **username**: Your username
    - **password**: Your password
    
    Returns a JWT token and user information.
    """
    # Find user by username
    user = db.query(User).filter(User.username == credentials.username).first()
    
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"User logged in: {user.username} (ID: {user.id})")
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user information.
    
    Requires valid JWT token in Authorization header.
    """
    return UserResponse.model_validate(current_user)


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout the current user.
    
    Note: With JWT tokens, actual logout is handled on the client side
    by deleting the token. This endpoint is mainly for consistency
    and can be used for logging purposes.
    """
    logger.info(f"User logged out: {current_user.username} (ID: {current_user.id})")
    
    return {"message": "Successfully logged out"}
