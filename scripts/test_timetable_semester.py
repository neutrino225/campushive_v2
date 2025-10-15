#!/usr/bin/env python3
"""
Quick test script for timetable agent semester course lookup functionality.
"""

import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from langchain_core.messages import HumanMessage
from multiagent.agents.timetable_agent import TimetableAgentBuilder

def test_semester_lookup():
    """Test the lookup_semester_courses tool."""
    print("=" * 80)
    print("Testing Timetable Agent with Semester Course Lookup")
    print("=" * 80)
    
    # Build the agent
    builder = TimetableAgentBuilder(
        timetable_path=str(root / "data" / "structured_timetable.csv"),
        mapping_path=str(root / "data" / "mappings.json"),
    )
    agent = builder.get_agent()
    
    config = {"configurable": {"thread_id": "test_semester_lookup"}}
    
    # Test query 1: 7th semester BS AI student asking for timetable
    query1 = "Im a 7th semester BS AI Student provide me my complete timetable"
    
    print(f"\n📝 Query 1: {query1}\n")
    print("-" * 80)
    print("Agent Response:\n")
    
    messages = []
    for step in agent.stream(
        {"messages": [HumanMessage(content=query1)]},
        config,
        stream_mode="values",
    ):
        messages = step.get("messages", [])
        last_message = messages[-1]
        
        # Print only final AI messages
        if hasattr(last_message, 'content') and last_message.type == 'ai':
            # Only print if this is a new message (not a tool call)
            if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
                print(last_message.content)
                print()
    
    # Test query 2: Follow-up with section and elective info
    print("\n" + "=" * 80)
    query2 = "I'm in section AI-D and I'm taking Cloud Computing (AI4013) and Professional Practices in IT (CS4021) as electives"
    
    print(f"\n📝 Query 2: {query2}\n")
    print("-" * 80)
    print("Agent Response:\n")
    
    for step in agent.stream(
        {"messages": messages + [HumanMessage(content=query2)]},
        config,
        stream_mode="values",
    ):
        last_message = step.get("messages", [])[-1]
        
        # Print only final AI messages
        if hasattr(last_message, 'content') and last_message.type == 'ai':
            if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
                print(last_message.content)
                print()

if __name__ == "__main__":
    test_semester_lookup()
