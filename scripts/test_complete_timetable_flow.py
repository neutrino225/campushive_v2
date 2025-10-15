#!/usr/bin/env python3
"""
Test the exact user query: "Im a 7th semester BS AI Student provide me my complete timetable"
This simulates a complete conversation flow.
"""

import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from langchain_core.messages import HumanMessage, SystemMessage
from multiagent.agents.timetable_agent import TimetableAgentBuilder

def main():
    print("=" * 80)
    print("Complete Timetable Agent Test - User Query Simulation")
    print("=" * 80)
    
    # Build the agent
    builder = TimetableAgentBuilder(
        timetable_path=str(root / "data" / "structured_timetable.csv"),
        mapping_path=str(root / "data" / "mappings.json"),
    )
    agent = builder.get_agent()
    
    config = {"configurable": {"thread_id": "user_test_session"}}
    
    # Conversation turn 1
    print("\n" + "🧑 USER: Im a 7th semester BS AI Student provide me my complete timetable")
    print("-" * 80)
    
    messages = [
        SystemMessage(content=builder.system_prompt),
        HumanMessage(content="Im a 7th semester BS AI Student provide me my complete timetable")
    ]
    
    for step in agent.stream(
        {"messages": messages},
        config,
        stream_mode="values",
    ):
        messages = step.get("messages", [])
        last_message = messages[-1]
        
        if hasattr(last_message, 'content') and last_message.type == 'ai':
            if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
                print(f"\n🤖 AGENT:\n{last_message.content}\n")
    
    # Conversation turn 2 - User provides section
    print("\n" + "🧑 USER: I'm in AI-D section")
    print("-" * 80)
    
    messages.append(HumanMessage(content="I'm in AI-D section"))
    
    for step in agent.stream(
        {"messages": messages},
        config,
        stream_mode="values",
    ):
        messages = step.get("messages", [])
        last_message = messages[-1]
        
        if hasattr(last_message, 'content') and last_message.type == 'ai':
            if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
                print(f"\n🤖 AGENT:\n{last_message.content}\n")
    
    # Conversation turn 3 - User provides complete elective list
    print("\n" + "🧑 USER: My electives are: Cloud Computing (AI4013), Deep Learning (AI4023), Reinforcement Learning (AI4033), and Organizational Behavior (MG4002)")
    print("-" * 80)
    
    messages.append(HumanMessage(content="My electives are: Cloud Computing (AI4013), Deep Learning (AI4023), Reinforcement Learning (AI4033), and Organizational Behavior (MG4002)"))
    
    for step in agent.stream(
        {"messages": messages},
        config,
        stream_mode="values",
    ):
        messages = step.get("messages", [])
        last_message = messages[-1]
        
        if hasattr(last_message, 'content') and last_message.type == 'ai':
            if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
                print(f"\n🤖 AGENT:\n{last_message.content}\n")
    
    print("=" * 80)
    print("✅ Test complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()
