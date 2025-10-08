#!/usr/bin/env python3
"""
Database initialization script.
Creates all tables in the database.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import Base, engine
from app.database.models import User, ChatSession, ChatMessage
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db():
    """Initialize the database by creating all tables."""
    logger.info("Creating database tables...")
    
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Database tables created successfully!")
        logger.info(f"✓ Database location: {engine.url}")
        
        # List created tables
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"✓ Created tables: {', '.join(tables)}")
        
    except Exception as e:
        logger.error(f"✗ Error creating database tables: {e}")
        raise


if __name__ == "__main__":
    init_db()
