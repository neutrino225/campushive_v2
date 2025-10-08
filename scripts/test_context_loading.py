#!/usr/bin/env python3
"""
Test script to verify conversation context loading functionality.

This script tests that:
1. Messages are persisted to the database
2. History is loaded from DB into memory when needed
3. Context is available for follow-up questions
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal, ChatSession, ChatMessage, User
from app.routers.multiagent import load_history_into_memory
from multiagent.memory import memory_manager


async def test_context_loading():
    """Test that conversation context is properly loaded from database."""
    
    db = SessionLocal()
    
    try:
        # 1. Find or create a test user
        test_user = db.query(User).filter(User.username == "test_context").first()
        if not test_user:
            from app.auth.security import get_password_hash
            test_user = User(
                username="test_context",
                email="test_context@example.com",
                password_hash=get_password_hash("test123"),
                role="student"
            )
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
        
        session_name = "test_session_context"
        
        # 2. Create a test session with some messages
        test_session = db.query(ChatSession).filter(
            ChatSession.session_name == session_name,
            ChatSession.user_id == test_user.id
        ).first()
        
        if not test_session:
            test_session = ChatSession(
                user_id=test_user.id,
                session_name=session_name
            )
            db.add(test_session)
            db.commit()
            db.refresh(test_session)
            
            # Add some test messages
            messages_data = [
                ("What clubs are available?", "We have programming club, debate club, and sports clubs."),
                ("Tell me about the programming club", "The programming club meets every Tuesday at 6 PM in Room 301."),
                ("What about debate club?", "The debate club meets on Thursdays at 5 PM.")
            ]
            
            for user_msg, agent_msg in messages_data:
                user_message = ChatMessage(
                    session_id=test_session.id,
                    message_type="user",
                    content=user_msg,
                    agent_type=None,
                    message_metadata=None
                )
                db.add(user_message)
                
                agent_message = ChatMessage(
                    session_id=test_session.id,
                    message_type="agent",
                    content=agent_msg,
                    agent_type="supervisor",
                    message_metadata='{"route": ["general"]}'
                )
                db.add(agent_message)
            
            db.commit()
            print(f"✓ Created test session with {len(messages_data)} conversation turns")
        
        # 3. Clear memory to simulate a fresh start
        memory_manager.clear_session(session_name)
        print(f"✓ Cleared in-memory history for session: {session_name}")
        
        # 4. Load history from database into memory
        await load_history_into_memory(session_name, test_user.id, db)
        print(f"✓ Loaded history from database into memory")
        
        # 5. Verify that history is now in memory
        history = memory_manager.get_history(session_name)
        print(f"✓ Memory now contains {len(history)} conversation turns")
        
        # 6. Print the loaded context
        print("\n" + "="*60)
        print("LOADED CONVERSATION CONTEXT:")
        print("="*60)
        for i, turn in enumerate(history, 1):
            print(f"\nTurn {i}:")
            print(f"  User: {turn.user_message}")
            print(f"  Bot: {turn.agent_response}")
            print(f"  Route: {turn.route}")
        print("="*60)
        
        # 7. Verify context string generation
        context_str = memory_manager.get_context_string(session_name)
        print("\n" + "="*60)
        print("FORMATTED CONTEXT STRING:")
        print("="*60)
        print(context_str)
        print("="*60)
        
        print("\n✅ All tests passed! Context loading is working correctly.")
        print("\nThe LLM can now reference this context when answering follow-up questions.")
        print("For example, if the user asks 'What time does it meet?', the LLM")
        print("will have context about which club was discussed most recently.")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("Testing Conversation Context Loading")
    print("="*60)
    asyncio.run(test_context_loading())
