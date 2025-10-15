#!/usr/bin/env python3
"""
Test the Generative AI vs PF matching issue.
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
    print("Testing Generative AI vs PF Matching")
    print("=" * 80)
    
    # Build the agent
    builder = TimetableAgentBuilder(
        timetable_path=str(root / "data" / "structured_timetable.csv"),
        mapping_path=str(root / "data" / "mappings.json"),
    )
    agent = builder.get_agent()
    
    config = {"configurable": {"thread_id": "genai_pf_test"}}
    
    # Test the exact query from the user
    query = "When are classes for Computer Vision AI A and OBL AI D and Generative AI CS A"
    
    print(f"\n📝 Query: {query}\n")
    print("-" * 80)
    print("Agent Response:\n")
    
    messages = [
        SystemMessage(content=builder.system_prompt),
        HumanMessage(content=query)
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
                print(f"{last_message.content}\n")
    
    print("=" * 80)
    print("✅ Test complete! Check if 'Gen AI' is shown instead of 'PF'")
    print("=" * 80)

if __name__ == "__main__":
    main()
