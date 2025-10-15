#!/usr/bin/env python3
"""
Test the smart course search functionality.
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
    print("Testing Smart Course Search")
    print("=" * 80)
    
    # Build the agent
    builder = TimetableAgentBuilder(
        timetable_path=str(root / "data" / "structured_timetable.csv"),
        mapping_path=str(root / "data" / "mappings.json"),
    )
    agent = builder.get_agent()
    
    config = {"configurable": {"thread_id": "smart_search_test"}}
    
    test_queries = [
        "Show me all Computer Vision courses",
        "What ML courses are available for AI section A?",
        "I need the timetable for Computer Vision AI-A"
    ]
    
    for query in test_queries:
        print(f"\n{'='*80}")
        print(f"🧑 USER: {query}")
        print("-" * 80)
        
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
                    print(f"\n🤖 AGENT:\n{last_message.content}\n")
        
        # Reset for next query
        config = {"configurable": {"thread_id": f"smart_search_test_{test_queries.index(query)}"}}
    
    print("=" * 80)
    print("✅ Smart search tests complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()
