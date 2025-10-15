# Fix: Generative AI vs PF Matching Issue

## Problem

User query: `"When are classes for Computer Vision AI A and OBL AI D and Generative AI CS A"`

**Issue:** Timetable agent was incorrectly matching "Generative AI CS-A" to "PF (CS-A)" (Programming Fundamentals).

## Root Causes

### 1. Keyword-Based Filtering Missing

The fuzzy matching algorithm was matching based primarily on section codes (CS-A) without checking if the actual course keywords matched. This caused:

- "Generative AI CS-A" → matched "PF (CS-A)" ❌
- Both have "CS-A" section, but completely different courses

### 2. System Prompt Not Injected

The timetable agent's intelligent system prompt wasn't being injected when called through the student node, causing:

- Labs not auto-included
- No alternative section suggestions
- Basic retrieval behavior instead of agent-like behavior

### 3. Abbreviation Expansion Order

"Generative AI" wasn't being normalized to "Gen AI" early enough in the pipeline.

## Solutions Implemented

### Fix 1: Keyword-Based Pre-Filtering

Added `_filter_by_keywords()` method that:

- Extracts significant keywords from query (excluding section codes)
- Checks for abbreviation matches (gen → generative, pf → programming fundamentals)
- Applies strong negative filtering:
  - If query contains "generative" or "gen ai", REJECT courses with "pf" but no "gen"
  - If query contains "pf" or "programming", REJECT courses with "gen" but no "pf"

**Code:**

```python
def _filter_by_keywords(self, query: str, candidates: List[str]) -> List[str]:
    """Filter candidates by checking if key course terms match."""
    # Extract keywords, expand abbreviations
    # Check for strong negative matches (prevent wrong course)
    # If query has "generative", don't match "pf" courses
    # If query has "pf", don't match "gen ai" courses
```

### Fix 2: Enhanced Normalization

Added course name expansion in `_normalize()`:

```python
# Course name expansions (for better matching)
text = text.replace("generative ai", "gen ai")
text = text.replace("generative artificial intelligence", "gen ai")

# Remove group identifiers like "G-1", "G-2"
text = re.sub(r'\bg-\d+\b', '', text)
```

This ensures:

- "Generative AI CS-A" → "gen ai cs a"
- "Gen AI (CS-A, G-1)" → "gen ai cs a" (after normalization)
- Perfect match! ✅

### Fix 3: System Prompt Injection

Modified `student.py` timetable_node to inject system prompt:

```python
# Get the system prompt from the builder
system_prompt = getattr(agent_builder, 'system_prompt', '')

# Inject system prompt for intelligent agent behavior
messages = [HumanMessage(content=question)]
if system_prompt:
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=question)]

for step in agent.stream({"messages": messages}, config_dict, stream_mode="values"):
```

This enables:

- Auto-inclusion of labs/tutorials
- Alternative section suggestions
- Smart explanations
- Agent-like conversational behavior

### Fix 4: Tool Decorator Consistency

Changed timetable tools from `Tool()` wrapper to direct `@tool` decorated functions:

```python
# OLD (caused Groq API errors):
Tool(name="get_timetables", func=get_timetables, description="...")

# NEW (works with Groq):
get_timetables  # Already @tool decorated
```

## Test Results

### Before Fix:

```
Query: "Computer Vision AI A and OBL AI D and Generative AI CS A"

Response:
- Computer Vision: ✅ Found (but no lab)
- OBL: ❌ Not found
- Generative AI: ❌ Matched to "PF (CS-A)" - WRONG COURSE!
```

### After Fix:

```
Query: "Computer Vision AI A and OBL AI D and Generative AI CS A"

Response:
Monday:
  11:30-12:50  Computer Vision (AI-A)  D-406
Tuesday:
  10:00-11:20  Generative AI (CS-A, G-1)  D-315  ✅ CORRECT!
  01:00-02:20  Organizational Behavior (OBL) (AI-D)  D-403  ✅ CORRECT!
Wednesday:
  08:30-09:50  Computer Vision Lab (AI-A)  C-Rawal 4  ✅ AUTO-INCLUDED!
  11:30-12:50  Computer Vision (AI-A)  D-412
Thursday:
  10:00-11:20  Generative AI (CS-A, G-1)  D-313  ✅ CORRECT!
  01:00-02:20  Organizational Behavior (OBL) (AI-D)  D-405  ✅ CORRECT!
```

## Files Modified

1. **`multiagent/agents/timetable_agent.py`**

   - Added `_filter_by_keywords()` method
   - Enhanced `_normalize()` with course name expansion
   - Added G-1/G-2 group code removal
   - Changed tools list to use @tool decorated functions directly

2. **`multiagent/nodes/student.py`**
   - Modified `timetable_node()` to inject system prompt
   - Get agent_builder instance to access system_prompt attribute
   - Prepend SystemMessage with prompt before HumanMessage

## Debug Scripts Created

- `scripts/debug_matching.py` - Test normalization and fuzzy matching
- `scripts/debug_phrase_extraction.py` - Test multi-course query parsing
- `scripts/test_genai_pf_issue.py` - End-to-end test for the specific issue

## Key Learnings

1. **Keyword Filtering is Critical:** Fuzzy matching alone isn't enough - need semantic understanding of what makes courses different
2. **System Prompts Matter:** Without the system prompt, the agent reverts to basic retrieval behavior
3. **Abbreviation Handling:** Must handle both directions (gen→generative, generative→gen) for robust matching
4. **Tool Decorators:** Always use `@tool` decorator instead of `Tool()` wrapper for Groq API compatibility

## Future Improvements

1. **LLM-Based Course Disambiguation:** Use small_llm to semantically compare courses when section codes match
2. **Course Synonym Database:** Maintain explicit mappings of course variations
3. **Confidence Scoring:** Add confidence scores to matches and warn user when confidence is low
4. **Smart Corrections:** "Did you mean 'Gen AI' instead of 'PF'?" when detecting potential confusion

## Conclusion

✅ **Issue Resolved:** Generative AI now correctly matches to "Gen AI (CS-A, G-1)" and does NOT match to "PF (CS-A)".

✅ **Enhanced Behavior:** Agent now auto-includes labs, provides intelligent suggestions, and acts conversationally.

✅ **Root Causes Fixed:**

1. Keyword-based pre-filtering prevents wrong course matches
2. System prompt injection enables intelligent agent behavior
3. Enhanced normalization handles abbreviations and group codes
4. Tool decorator consistency fixes Groq API errors
