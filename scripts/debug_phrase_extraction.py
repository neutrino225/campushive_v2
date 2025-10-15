#!/usr/bin/env python3
"""
Test how the agent parses multi-course queries.
"""

import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from multiagent.agents.timetable_agent import TimetableAgentBuilder

def main():
    print("=" * 80)
    print("Debug Course Phrase Extraction")
    print("=" * 80)
    
    # Build the agent
    builder = TimetableAgentBuilder(
        timetable_path=str(root / "data" / "structured_timetable.csv"),
        mapping_path=str(root / "data" / "mappings.json"),
    )
    
    # Test the full query as the agent would receive it
    full_query = "Computer Vision AI A and OBL AI D and Generative AI CS A"
    
    print(f"\n📝 Full Query: '{full_query}'")
    print("\n🔍 Extracted Phrases:")
    phrases = builder._extract_course_phrases(full_query)
    for i, phrase in enumerate(phrases, 1):
        print(f"  {i}. '{phrase}'")
    
    print("\n🔍 Testing Each Phrase for Matches:")
    for phrase in phrases:
        matched, suggestions = builder._fuzzy_match_courses(phrase)
        print(f"\n  Phrase: '{phrase}'")
        print(f"  Matched: {matched if matched else 'None'}")
        if suggestions:
            print(f"  Suggestions: {suggestions[:2]}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
