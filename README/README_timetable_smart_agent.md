# Timetable Agent - Smart Enhancement Summary

## 🎯 Objective

Transform the timetable agent from a simple retrieval tool into an intelligent assistant that understands context, provides proactive suggestions, and acts like a real agent.

## ✨ Key Enhancements

### 1. Auto-Inclusion of Related Courses

**Problem:** User asks for "Computer Vision AI-A" but forgets about the lab  
**Solution:** `_expand_course_with_related()` method automatically finds and includes labs, tutorials, practicals

**Code:**

```python
def _expand_course_with_related(self, matched_courses: Set[str]) -> Set[str]:
    """Expand matched courses to include related courses (labs, tutorials, etc.)."""
    for course in matched_courses:
        # Look for related courses (lab, tutorial, recitation)
        for potential_course in self.data_df["Class"].unique():
            if any(keyword in potential_lower for keyword in ['lab', 'tutorial', 'recitation', 'practical']):
                # Match base names and auto-include
```

**Result:**

- Query: "Computer Vision AI-A"
- Returns: Lecture (Mon 11:30-12:50, Wed 11:30-12:50) + Lab (Wed 8:30-9:50) ✅

### 2. Alternative Section Suggestions

**Problem:** User in AI-D asks for "Cloud Computing AI-D" but it's only offered in AI-A, AI-B  
**Solution:** `_get_alternative_sections()` finds same course in different sections

**Code:**

```python
def _get_alternative_sections(self, course_name: str, original_section: str) -> List[Tuple[str, str]]:
    """Find alternative sections offering the same course."""
    # Extract base course name without section
    # Search for similar courses in different sections
    # Return list of (full_course_name, section)
```

**Result:**

- Agent response: "Cloud Computing isn't in AI-D, but I found it in:

  - AI-A: Mon 14:30-15:50 (D-406)
  - AI-B: Mon 13:00-14:20 (D-411)

  Would you like to enroll in one of these?" ✅

### 3. LLM-Powered Smart Search

**Problem:** User queries are ambiguous: "ML courses", "computer vision stuff"  
**Solution:** `smart_course_search` tool uses small_llm to parse intent and find matches

**Code:**

```python
@tool
def smart_course_search(query: str) -> str:
    """Use AI to intelligently search for courses in the timetable."""
    # Parse query with small_llm to extract:
    # - Course name
    # - Section preference
    # - Whether to include labs
    # - Search keywords

    # Match courses using keywords and scoring
    # Return formatted list with lab indicators
```

**Result:**

- Query: "What ML courses are available for AI section A?"
- Returns: ML (AI-A), ML Lab (AI-A), Cloud MLOps (AI-A), Reinf Learning (AI-A), Adv Gen AI (AI-A), etc. ✅

### 4. Intelligent Response Generation

**Problem:** Agent just says "not found" - not helpful!  
**Solution:** Enhanced `get_timetables` tool provides smart responses

**Scenarios Handled:**

**A. All courses found:**

```
Here is your complete timetable, grouped by day:
[Full schedule]
```

**B. Some courses found, some missing:**

```
Here's what I found for your timetable:
[Partial schedule]

⚠️ Some courses couldn't be found:
- Cloud Computing AI-D: Not available in this section, but found in: AI-A, AI-B
- Deep Learning AI-D: Not found in timetable

💡 Would you like me to:
1. Show timetables for alternative sections?
2. Help you find when these electives are offered?
```

**C. No courses found - with alternatives:**

```
I couldn't find those courses in your section, but I found alternatives:

**Cloud Computing AI-D** is available in:
  - Section AI-A
  - Section AI-B

💡 Would you like me to show the timetable for any of these sections?
```

**D. No courses found - with tips:**

```
I couldn't find any matching courses in the timetable.

💡 Tips:
- Use full course names (e.g., 'Computer Vision' not 'CV')
- Include section (e.g., 'AI-D', 'CS-A')
- Check if the course is offered this semester
- Try: 'What courses are available for AI section D?'
```

### 5. Agent-Like System Prompt

**Old Approach:** "You are a timetable retrieval tool"  
**New Approach:** "You are an INTELLIGENT assistant - explain, suggest, guide"

**Key Instructions:**

- Auto-include related courses (labs) ✓
- When courses missing, explain WHY and offer alternatives ✓
- Be proactive - suggest what user might have forgotten ✓
- Use alternative suggestions from tools ✓
- Don't just return data - provide context and options ✓

## 📊 Test Results

### Test 1: Auto Lab Inclusion

**Query:** "Timetable for Computer Vision AI-A"

**Response:**

```
Here's the timetable for Computer Vision AI-A (including the automatically added lab):

| Day       | Course                    | Time          | Room      |
|-----------|---------------------------|---------------|-----------|
| Monday    | Computer Vision AI-A      | 11:30 – 12:50 | D-406     |
| Wednesday | Computer Vision Lab AI-A  | 08:30 – 09:50 | C-Rawal 4 |
| Wednesday | Computer Vision AI-A      | 11:30 – 12:50 | D-412     |
```

✅ **PASSED** - Lab automatically included!

### Test 2: Alternative Sections with Smart Suggestions

**Query:** "I'm in 7th semester BS AI, AI-D section. Electives: Cloud Computing, Deep Learning, Reinforcement Learning, Organizational Behavior"

**Response:**

```
### Your 7th-semester BS AI – AI-D timetable (so far)

| Day      | Time         | Course (Section)            | Room      |
|----------|--------------|----------------------------|-----------|
| Monday   | 10:00-11:20  | Computer Vision (AI-D)     | D-406     |
| Wednesday| 10:00-11:20  | Computer Vision (AI-D)     | D-412     |
| Thursday | 14:30-15:50  | Computer Vision Lab (AI-D) | A-Mehran1 |
| Tuesday  | 13:00-14:20  | Organizational Behavior    | D-403     |
| Thursday | 13:00-14:20  | Organizational Behavior    | D-405     |

## What's missing for the electives you listed?

| Elective              | Offered in AI-D? | Where it IS offered       | Typical slot      |
|-----------------------|------------------|---------------------------|-------------------|
| Cloud Computing       | No               | AI-A, AI-B                | Mon afternoons    |
| Deep Learning         | No               | CS-A, CS-B, DS-A          | Tue/Thu/Fri       |
| Reinforcement Learning| No               | AI-A, AI-B                | Wed afternoons    |
| Org Behavior          | Yes              | Already scheduled         | —                 |

### Why they aren't in AI-D
The timetable shows Cloud Computing, Deep Learning, and Reinforcement Learning
are not taught for AI-D section this semester.

## Your options:
1. Cross-section enrollment - Take from AI-A/AI-B (check for time conflicts)
2. Swap for AI-D-offered electives
3. Drop these electives this semester

Quick look at alternative slots:
| Course                | Section | Day & Time      | Room  |
|-----------------------|---------|-----------------|-------|
| Cloud Computing       | AI-A    | Mon 14:30-15:50 | D-406 |
| Cloud Computing       | AI-B    | Mon 13:00-14:20 | D-411 |
| Deep Learning         | CS-A    | Tue 10:00-11:20 | G-2   |
| Reinforcement Learning| AI-A    | Wed 14:30-15:50 | D-410 |

## Next steps
- Tell me which alternative sections you'd like to enroll in
- Or let me know if you'd rather pick different AI-D electives
```

✅ **PASSED** - Intelligent, comprehensive, actionable!

### Test 3: Smart Course Search

**Query:** "What ML courses are available for AI section A?"

**Response:**

```
Here are the machine-learning-related courses offered in AI-A:

| Course                        | Type    |
|------------------------------|---------|
| ML (AI-A)                    | Lecture |
| ML Lab (AI-A)                | Lab     |
| Cloud MLOps (AI-A)           | Lecture |
| Reinf Learning (AI-A)        | Lecture |
| Adv Gen AI (AI-A)            | Lecture |
| Data St (AI-A/C)             | Lecture |
| Prog for AI (AI-A)           | Lecture |

**What to do next**
- Tell me which courses you want the timetable for
- ML Lab will be included automatically with ML
- I can show AI-B or AI-C sections if times don't work
```

✅ **PASSED** - Smart search with contextual suggestions!

## 🔧 Technical Implementation

### Files Modified:

- `/home/neutrino/projects/campushive_v2/multiagent/agents/timetable_agent.py`

### New Methods:

1. `_expand_course_with_related()` - Auto-find labs/tutorials
2. `_get_alternative_sections()` - Find same course in other sections
3. `smart_course_search` tool - LLM-powered intelligent search

### Enhanced Methods:

1. `_extract_course_schedule()` - Now calls expand_course_with_related
2. `get_timetables()` - Smart response generation with alternatives
3. System prompt - Agent-like behavior instructions

### New Tools Added:

- `smart_course_search` - AI-powered course discovery

### Dependencies:

- `small_llm` from `config.py` - For query parsing
- `json` and `re` - For JSON extraction and pattern matching

## 📈 Improvements Summary

| Aspect             | Before           | After                               |
| ------------------ | ---------------- | ----------------------------------- |
| Lab Inclusion      | Manual           | Automatic ✅                        |
| Missing Courses    | "Not found"      | Smart alternatives + explanation ✅ |
| Search             | Exact match only | LLM-powered fuzzy + semantic ✅     |
| Response Style     | Data dump        | Conversational + actionable ✅      |
| Cross-Section Help | None             | Full suggestions with times ✅      |
| User Guidance      | Minimal          | Proactive tips and options ✅       |

## 🎯 Agent Behavior Examples

### Scenario 1: Forgotten Lab

**User:** "Show Computer Vision AI-D"  
**Old Agent:** [Shows only lecture]  
**New Agent:** "Here's Computer Vision AI-D with the lab (auto-included): [Lecture Mon/Wed + Lab Thu]" ✅

### Scenario 2: Wrong Section

**User:** "Cloud Computing AI-D"  
**Old Agent:** "Not found"  
**New Agent:** "Cloud Computing isn't in AI-D, but it's in AI-A (Mon 2:30pm) and AI-B (Mon 1pm). Want to see those?" ✅

### Scenario 3: Ambiguous Query

**User:** "ML stuff for AI section"  
**Old Agent:** [Confusion]  
**New Agent:** "Found 7 ML-related courses in AI-A: ML, ML Lab, Cloud MLOps, Reinforcement Learning... Which ones do you need?" ✅

## 🚀 Future Enhancements

1. **Conflict Detection:** Check for time clashes across selected courses
2. **Room Navigation:** Provide building/room maps
3. **Professor Info:** Link courses to faculty teaching them
4. **Historical Data:** Suggest based on what students typically take together
5. **Waitlist Info:** Show if alternative sections have space

## 📝 Documentation

- Main README: `/home/neutrino/projects/campushive_v2/README/README_timetable_semester_lookup.md`
- This file: Enhanced smart agent capabilities
- Test scripts:
  - `scripts/test_complete_timetable_flow.py` - Full conversation flow
  - `scripts/test_smart_search.py` - Smart search capabilities

## ✅ Conclusion

The timetable agent is now a true **intelligent assistant** that:

- ✅ Understands context (auto-includes labs)
- ✅ Provides alternatives (cross-section options)
- ✅ Explains reasoning (why courses aren't available)
- ✅ Offers actionable steps (what to do next)
- ✅ Uses AI for smart search (LLM-powered)
- ✅ Acts conversationally (not just data retrieval)

**The agent is no longer just a tool - it's a helpful advisor!**
