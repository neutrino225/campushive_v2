# Timetable Agent: Critical Fixes

## Overview

This document details three critical bugs that were fixed in the timetable agent to enable proper multi-course queries and prevent FYP flooding.

## Bug 1: Phrase Extraction Failure (Comma Separator Issue)

### Problem

When users requested multiple courses (e.g., "Computer Vision AI-A, Agentic AI AI-A, Org Behavior AI-A"), only the FIRST course was found.

### Root Cause

The `_extract_course_phrases()` method was normalizing the query BEFORE splitting on commas. The `_normalize()` function removes all punctuation (including commas), so by the time the split happened, all commas were already gone and the entire query was treated as one phrase.

**Before:**

```python
def _extract_course_phrases(self, query: str) -> List[str]:
    normalized_query = self._normalize(query)  # ❌ Commas removed here!
    parts = re.split(r'(\band\b|,|;|\n)', normalized_query)  # Too late!
```

**Example:**

```python
Query: "agentic ai ai-a, org behavior ai-a"
After normalize: "agentic ai ai a org behavior ai a"  # Comma gone!
After split: ["agentic ai ai a org behavior ai a"]    # One phrase!
```

### Solution

Split on separators FIRST, then normalize each phrase separately.

```python
def _extract_course_phrases(self, query: str) -> List[str]:
    # IMPORTANT: Split BEFORE normalization to preserve separators
    parts = re.split(r'(\band\b|,|;|\n)', query)  # ✅ Split first!

    # Filter out separators
    phrases = [p.strip() for p in parts if p.strip() and p not in ["and", ",", ";", "\n"]]

    # Normalize each phrase separately AFTER splitting
    phrases = [self._normalize(p) for p in phrases]  # ✅ Normalize after!
```

**After fix:**

```python
Query: "agentic ai ai-a, org behavior ai-a"
After split: ["agentic ai ai-a", "org behavior ai-a"]    # Two phrases!
After normalize: ["agentic ai ai a", "org behavior ai a"] # Both preserved!
```

**Files Modified:** `multiagent/agents/timetable_agent.py` (lines 125-134)

---

## Bug 2: Phrase Matching Logic Error (Join Then Match)

### Problem

Even after splitting phrases correctly, only ONE course was matched when multiple courses were provided.

### Root Cause

The `_extract_course_schedule()` method was joining all course patterns into ONE string and trying to fuzzy match that combined string.

**Before:**

```python
def _extract_course_schedule(self, query: str):
    course_candidates = []
    for phrase in phrases:
        patterns = self._recognize_course_patterns(phrase)
        course_candidates.extend(patterns)

    # ❌ Join all patterns into one string - creates gibberish!
    matched_courses, suggestions = self._fuzzy_match_courses(" ".join(course_candidates))
```

**Example:**

```python
Phrases: ["agentic ai ai a", "org behavior ai a"]
Patterns: ["agentic ai ai a", "org behavior ai a"]
Joined: "agentic ai ai a org behavior ai a"  # ❌ Gibberish!
Fuzzy match: Finds "Agentic AI (AI-A)" (partial match)
Result: ONLY Agentic AI matched, Org Behavior lost!
```

### Solution

Match each phrase individually, don't join them.

```python
def _extract_course_schedule(self, query: str):
    matched_courses = set()
    suggestions = []

    # ✅ Match each phrase individually
    for phrase in phrases:
        patterns = self._recognize_course_patterns(phrase)

        for pattern in patterns:
            matches, suggs = self._fuzzy_match_courses(pattern)
            matched_courses.update(matches)  # ✅ Accumulate all matches
            suggestions.extend(suggs)
```

**After fix:**

```python
Phrase 1: "agentic ai ai a" → Matches: ["Agentic AI (AI-A)"]
Phrase 2: "org behavior ai a" → Matches: ["Org Behavior (AI-A)"]
Result: Both courses found! ✅
```

**Files Modified:** `multiagent/agents/timetable_agent.py` (lines 500-510)

---

## Bug 3: FYP Flooding + Junk Lab Entries

### Problem

When students queried for semester timetables, the results were flooded with:

1. **FYP (Final Year Project)** sessions for every time slot (FYP is self-scheduled, shouldn't be in timetables)
2. **Junk entries** like `CourseTimetable(course='Lab', room='Lab', time='Room', day='Monday')`

### Root Cause

1. The CSV contains FYP entries without section codes, so they match ALL queries
2. The CSV contains malformed rows: `241,Monday,Room,Lab,Lab,,`

### Solution

Filter out both types of entries at the dataframe level.

```python
def _extract_course_schedule(self, query: str):
    filtered_df = self.data_df[self.data_df["Class"].isin(matched_courses)]

    # ✅ Filter out junk entries
    filtered_df = filtered_df[
        ~((filtered_df["Class"] == "Lab") &
          (filtered_df["Room"] == "Lab") &
          (filtered_df["Time"] == "Room"))
    ]

    # ✅ Filter out FYP - it's self-scheduled with supervisors
    filtered_df = filtered_df[
        ~filtered_df["Class"].str.contains("FYP|Final Year Project", case=False, na=False)
    ]
```

Additionally, updated the system prompt to emphasize this rule:

```python
self.system_prompt = """...
**⚠️ CRITICAL RULES:**
1. **NEVER include FYP (Final Year Project) in timetables** - FYP is self-scheduled with supervisors
2. **ALWAYS use lookup_semester_courses FIRST** when user mentions their semester
"""
```

**Files Modified:**

- `multiagent/agents/timetable_agent.py` (lines 520-532, lines 30-35)

---

## Testing & Validation

### Test 1: Multi-Course Query

```bash
Query: "Computer Vision AI-A, Agentic AI AI-A, Organizational Behavior AI-A"
Result: ✅ ALL THREE courses found with correct times/rooms
        ✅ Computer Vision Lab auto-included
        ✅ NO FYP entries
        ✅ NO junk Lab entries
```

### Test 2: Semester Query

```bash
Query: "7th semester BS AI section A, electives are agentic ai and organizational behavior"
Agent behavior: ✅ Calls lookup_semester_courses first
               ✅ Asks for missing elective details (AI Elective III/IV, SS/MG Elective II)
               ✅ Conversational and helpful
```

### Test 3: Direct Timetable Query

```bash
Query: "Show me timetable for Computer Vision AI-A, Agentic AI AI-A, Organizational Behavior AI-A"
Output: ✅ Complete weekly schedule with all 3 courses
        ✅ Grouped by day
        ✅ JSON export option included
        ✅ Computer Vision Lab automatically included
```

---

## Impact

**Before Fixes:**

- Multi-course queries only returned first course
- FYP flooded timetable results
- Junk "Lab, Lab, Room" entries polluted output
- User experience: Frustrating and broken

**After Fixes:**

- Multi-course queries work perfectly ✅
- FYP excluded from all timetables ✅
- Clean, professional output ✅
- User experience: Intelligent and helpful ✅

---

## Related Documentation

- [Timetable Smart Agent](README_timetable_smart_agent.md)
- [Gen AI vs PF Fix](README_genai_pf_fix.md)
- [Semester Course Lookup](README_timetable_semester_lookup.md)
