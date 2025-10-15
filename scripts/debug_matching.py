#!/usr/bin/env python3
"""
Simple test to debug why OBL and Gen AI aren't matching.
"""

import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from multiagent.agents.timetable_agent import TimetableAgentBuilder

def main():
    print("=" * 80)
    print("Debug Fuzzy Matching")
    print("=" * 80)
    
    # Build the agent
    builder = TimetableAgentBuilder(
        timetable_path=str(root / "data" / "structured_timetable.csv"),
        mapping_path=str(root / "data" / "mappings.json"),
    )
    
    # Test normalization
    test_queries = [
        "OBL AI-D",
        "Org Behavior AI-D",
        "Organizational Behavior AI-D",
        "Generative AI CS-A",
        "Gen AI CS-A",
    ]
    
    print("\n📝 Testing Normalization:")
    for query in test_queries:
        normalized = builder._normalize(query)
        print(f"  '{query}' → '{normalized}'")
    
    # Test fuzzy matching
    print("\n📝 Testing Fuzzy Matching:")
    for query in test_queries:
        matched, suggestions = builder._fuzzy_match_courses(query)
        print(f"\n  Query: '{query}'")
        print(f"  Matched: {matched if matched else 'None'}")
        if suggestions:
            print(f"  Suggestions: {suggestions[:3]}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
