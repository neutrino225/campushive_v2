from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash
import os
import logging

logger = logging.getLogger(__name__)

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production-use-env-variable")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Initialize Argon2id hasher with OWASP recommended parameters
ph = PasswordHasher(
    time_cost=2,        # Number of iterations (OWASP: 2 minimum)
    memory_cost=19456,  # 19 MiB memory (OWASP: 19 MiB minimum)
    parallelism=1,      # Single thread
    hash_len=32,        # 32-byte hash output
    salt_len=16         # 16-byte salt
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash using Argon2id.
    
    Args:
        plain_password: The plaintext password to verify
        hashed_password: The Argon2id hash to verify against
        
    Returns:
        bool: True if password matches, False otherwise
    """
    try:
        ph.verify(hashed_password, plain_password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHash) as e:
        logger.debug(f"Password verification failed: {type(e).__name__}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during password verification: {e}")
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password using Argon2id with OWASP recommended parameters.
    
    Args:
        password: The plaintext password to hash
        
    Returns:
        str: The Argon2id hash string
    """
    return ph.hash(password)


def needs_rehash(hashed_password: str) -> bool:
    """
    Check if a password hash needs to be rehashed with updated parameters.
    
    Args:
        hashed_password: The hash to check
        
    Returns:
        bool: True if rehashing is recommended, False otherwise
    """
    try:
        return ph.check_needs_rehash(hashed_password)
    except Exception:
        # If check fails, assume rehash is needed
        return True


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Dictionary containing token payload data
        expires_delta: Optional expiration time delta
    
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT access token.
    
    Args:
        token: JWT token string to decode
    
    Returns:
        Decoded token payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
