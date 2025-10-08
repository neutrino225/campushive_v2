#!/usr/bin/env python3
"""
Script to create an admin user.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal, User
from app.auth import get_password_hash
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_admin_user(username: str, email: str, password: str):
    """Create an admin user."""
    db = SessionLocal()
    
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            logger.error(f"✗ User '{username}' already exists!")
            return False
        
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            logger.error(f"✗ Email '{email}' already registered!")
            return False
        
        # Create admin user
        admin_user = User(
            username=username,
            email=email,
            password_hash=get_password_hash(password),
            role="admin"
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        logger.info(f"✓ Admin user created successfully!")
        logger.info(f"  Username: {admin_user.username}")
        logger.info(f"  Email: {admin_user.email}")
        logger.info(f"  Role: {admin_user.role}")
        logger.info(f"  ID: {admin_user.id}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Error creating admin user: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    import getpass
    
    print("=== Create Admin User ===\n")
    
    username = input("Enter username: ").strip()
    email = input("Enter email: ").strip()
    password = getpass.getpass("Enter password: ")
    password_confirm = getpass.getpass("Confirm password: ")
    
    if password != password_confirm:
        logger.error("✗ Passwords do not match!")
        sys.exit(1)
    
    if len(password) < 8:
        logger.error("✗ Password must be at least 8 characters long!")
        sys.exit(1)
    
    success = create_admin_user(username, email, password)
    sys.exit(0 if success else 1)
