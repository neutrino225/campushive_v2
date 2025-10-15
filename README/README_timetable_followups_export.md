# Timetable Agent: Follow-up Queries & Export Functionality

## Overview

The timetable agent now supports **intelligent follow-up queries** and **multiple export formats** without breaking existing functionality. This enables natural conversation flows like:

```
User: "Show me timetable for Computer Vision AI-A and Agentic AI AI-A"
Agent: [Shows timetable]

User: "Add Organizational Behavior AI-A to this"
Agent: [Updates timetable with new course]

User: "Sort it by time"
Agent: [Reorders entries by time]

User: "Export as Excel"
Agent: [Creates Excel file and provides download link]
```

---

## 🎯 New Features

### 1. Timetable Manipulation (`manipulate_timetable` tool)

Handles follow-up queries that modify existing timetables without regenerating from scratch.

**Supported Actions:**

| Action          | Description                       | Example User Query         |
| --------------- | --------------------------------- | -------------------------- |
| `add`           | Add courses to existing timetable | "Add Org Behavior AI-A"    |
| `remove`        | Remove courses matching keywords  | "Remove Computer Vision"   |
| `sort_by_time`  | Sort entries chronologically      | "Sort by time"             |
| `sort_by_day`   | Sort entries by day of week       | "Sort by day"              |
| `filter_by_day` | Show only specific day            | "Show only Monday classes" |

**How It Works:**

1. **Agent extracts timetable from conversation memory**

   - Previous AIMessage contains `additional_kwargs['data']` with JSON course list
   - Agent automatically passes this to the tool

2. **Tool performs manipulation**

   - Parses existing timetable JSON
   - Applies the requested action
   - Returns updated timetable with formatted message

3. **Result includes structured data**
   - New `additional_kwargs['data']` for next follow-up
   - Formatted markdown message for display

**Code Example:**

```python
@tool
def manipulate_timetable(action: str, courses: str, existing_timetable_json: str = "[]") -> AIMessage:
    """Manipulate an existing timetable (add/remove courses, sort, filter)."""
    # Parse existing
    existing_courses = json.loads(existing_timetable_json)

    if action == 'add':
        # Get new courses and append
        new_timetable, _ = self._extract_course_schedule(courses)
        existing_entries.extend(new_timetable.courses)

    elif action == 'remove':
        # Filter out matching courses
        remove_keywords = courses.lower().split()
        existing_entries = [e for e in existing_entries
                           if not any(kw in e.course.lower() for kw in remove_keywords)]

    # ... sort_by_time, sort_by_day, filter_by_day logic

    return AIMessage(content=formatted_message, additional_kwargs={"data": updated_data})
```

---

### 2. Export Functionality (`export_timetable` tool)

Exports timetables to various formats for external use.

**Supported Formats:**

| Format | Extension | Requirements         | Use Case                                 |
| ------ | --------- | -------------------- | ---------------------------------------- |
| CSV    | `.csv`    | None (built-in)      | Excel, Google Sheets, any spreadsheet    |
| Excel  | `.xlsx`   | `pandas`, `openpyxl` | Microsoft Excel, LibreOffice Calc        |
| iCal   | `.ics`    | `icalendar`, `pytz`  | Google Calendar, Apple Calendar, Outlook |
| PDF    | `.pdf`    | Not yet implemented  | Printing, sharing                        |

**How It Works:**

1. **Agent receives export request**

   - User says "Export as Excel" or "Download as CSV"
   - Agent calls `export_timetable` with format and timetable JSON

2. **Tool creates file**

   - Parses timetable data
   - Creates formatted export file
   - Saves to `data/timetable_exports/` directory

3. **Returns file path and instructions**
   - Shows full file path
   - Provides instructions for opening/importing

**CSV Export Example:**

```python
with open(filepath, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['Day', 'Time', 'Course', 'Room'])
    writer.writeheader()
    for course in courses:
        writer.writerow({
            'Day': course.get('day', ''),
            'Time': course.get('time_slot', ''),
            'Course': course.get('course', ''),
            'Room': course.get('room_number', '')
        })
```

**Excel Export Example:**

```python
import pandas as pd

df = pd.DataFrame([
    {
        'Day': c.get('day', ''),
        'Time': c.get('time_slot', ''),
        'Course': c.get('course', ''),
        'Room': c.get('room_number', '')
    }
    for c in courses
])

# Sort by day and time
day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
df['DayOrder'] = df['Day'].apply(lambda x: day_order.index(x) if x in day_order else 99)
df = df.sort_values(['DayOrder', 'Time']).drop('DayOrder', axis=1)

df.to_excel(filepath, index=False, sheet_name='Timetable')
```

**iCal Export Example:**

```python
from icalendar import Calendar, Event
from datetime import datetime, timedelta

cal = Calendar()
cal.add('prodid', '-//CampusHive Timetable//campushive.app//')
cal.add('version', '2.0')

for course_data in courses:
    event = Event()
    event.add('summary', course_name)
    event.add('location', room)
    event.add('dtstart', start_dt)
    event.add('dtend', end_dt)
    event.add('rrule', {'freq': 'weekly', 'until': semester_end})
    cal.add_component(event)

with open(filepath, 'wb') as f:
    f.write(cal.to_ical())
```

---

## 🧠 How the Agent Handles Follow-ups

### Conversation Memory Flow

1. **Initial Timetable Request**

   ```
   User: "Show timetable for Computer Vision AI-A"
   Agent: [Calls get_timetables] → Returns AIMessage with:
          - content: Formatted timetable markdown
          - additional_kwargs['data']: JSON list of courses
   ```

2. **Follow-up Query**

   ```
   User: "Add Agentic AI AI-A"
   Agent: [Looks at conversation history]
          [Finds previous AIMessage.additional_kwargs['data']]
          [Extracts timetable JSON]
          [Calls manipulate_timetable('add', 'Agentic AI AI-A', timetable_json)]
   ```

3. **Export Query**
   ```
   User: "Export as Excel"
   Agent: [Extracts current timetable from memory]
          [Calls export_timetable('excel', timetable_json)]
          → Returns file path and instructions
   ```

### System Prompt Guidance

The agent's system prompt now includes:

```
**🎯 Your Smart Capabilities:**
- **Conversation memory**: You remember previous timetables shown in this conversation
- **Timetable manipulation**: You can add/remove courses, sort, and filter existing timetables
- **Export support**: You can export timetables to PDF, Excel, iCal, or CSV formats

**Workflow for Follow-up Queries:**
5. **When user asks to modify existing timetable (FOLLOW-UP QUERIES):**
   - **Extract the timetable data** from conversation history:
     * Look for the previous AIMessage that contains additional_kwargs['data']
     * This contains the JSON list of courses from the last timetable
   - **Use manipulate_timetable tool** with appropriate action:
     * User: "Add Organizational Behavior AI-A" → action='add'
     * User: "Remove Computer Vision" → action='remove'
     * User: "Sort by time" → action='sort_by_time'
   - **IMPORTANT**: Always pass the existing timetable JSON to maintain continuity!

6. **When user asks to export timetable:**
   - **Use export_timetable tool** with format:
     * User: "Export as PDF" → export_timetable('pdf', timetable_json)
     * User: "Download as Excel" → export_timetable('excel', timetable_json)
```

---

## 📊 Technical Implementation

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  User Query: "Show timetable for Computer Vision AI-A"     │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  Agent: get_timetables("Computer Vision AI-A")             │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  Returns: AIMessage(                                        │
│    content="### Monday\n- Comp Vision...",                  │
│    additional_kwargs={                                      │
│      "data": [                                              │
│        {"course": "Comp Vision (AI-A)", "day": "Monday",   │
│         "time_slot": "11:30-12:50", "room_number": "D-406"}│
│      ]                                                      │
│    }                                                        │
│  )                                                          │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  User Query: "Add Agentic AI AI-A"                         │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  Agent: Extract previous timetable from memory              │
│         timetable_json = json.dumps(prev_msg.data)          │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  Agent: manipulate_timetable(                               │
│    action='add',                                            │
│    courses='Agentic AI AI-A',                               │
│    existing_timetable_json=timetable_json                   │
│  )                                                          │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  Returns: Updated AIMessage with both courses               │
│           (Computer Vision + Agentic AI)                    │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  User Query: "Export as Excel"                             │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  Agent: export_timetable(                                   │
│    format_type='excel',                                     │
│    timetable_json=current_timetable_json                    │
│  )                                                          │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  Returns: "✅ Excel file created at data/timetable_exports/ │
│            timetable_20251016.xlsx"                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧪 Testing & Validation

### Test 1: Add Course Follow-up

```python
# Initial timetable
builder._extract_course_schedule('Computer Vision AI-A, Agentic AI AI-A')
# Result: 5 entries (Computer Vision x2, Agentic AI x2, Comp Vision Lab x1)

# Add course
builder._extract_course_schedule('Organizational Behavior AI-A')
# Result: 2 entries (Org Behavior x2)

# Combined: 7 total entries ✅
```

### Test 2: CSV Export

```python
# Export timetable
export_timetable('csv', timetable_json, 'my_schedule')

# Result:
# ✅ File created: data/timetable_exports/my_schedule.csv
# Content:
# Day,Time,Course,Room
# Monday,11:30-12:50,Comp Vision (AI-A),D-406
# Monday,01:00-02:20,Agentic AI (AI-A),D-406
# ...
```

### Test 3: Excel Export

```python
# Export timetable
export_timetable('excel', timetable_json)

# Result:
# ✅ File created: data/timetable_exports/timetable_20251016_143022.xlsx
# DataFrame with sorted entries, ready to open in Excel ✅
```

---

## 📦 Dependencies

### Required (Built-in)

- `json` - JSON parsing
- `csv` - CSV export
- `os` - File operations
- `datetime` - Timestamp generation

### Optional (For Advanced Exports)

```bash
# For Excel export
pip install pandas openpyxl

# For iCal export
pip install icalendar pytz
```

**Graceful Degradation:**

- If pandas not installed → Falls back to CSV export with message
- If icalendar not installed → Suggests CSV/Excel with instructions
- PDF export → Not yet implemented, suggests alternatives

---

## 🎯 Benefits

### 1. **Natural Conversation Flow**

- ✅ Users can build timetables incrementally
- ✅ No need to repeat entire course list for modifications
- ✅ Agent remembers context across turns

### 2. **No Breaking Changes**

- ✅ Existing `get_timetables` functionality unchanged
- ✅ New tools are additional, not replacements
- ✅ System prompt enhanced, not rewritten

### 3. **Flexible Export Options**

- ✅ CSV works everywhere (no dependencies)
- ✅ Excel for professional formatting
- ✅ iCal for calendar integration
- ✅ All exports saved locally for easy access

### 4. **Smart Data Preservation**

- ✅ `additional_kwargs['data']` maintains structured data
- ✅ Follow-ups build on previous results
- ✅ Export uses same data structure

---

## 🚀 Usage Examples

### Example 1: Incremental Timetable Building

```
User: Show me timetable for Computer Vision AI-A
Agent: [Shows Computer Vision + Lab]

User: Add Agentic AI AI-A
Agent: ✅ Added courses to your timetable:
       ### Monday
       - Computer Vision (AI-A): 11:30-12:50 in D-406
       - Agentic AI (AI-A): 01:00-02:20 in D-406
       ...

User: Also add Organizational Behavior AI-A
Agent: ✅ Added courses... [shows all three]

User: Remove Computer Vision
Agent: ✅ Removed courses matching 'Computer Vision':
       [Shows only Agentic AI and Org Behavior]
```

### Example 2: Sorting and Filtering

```
User: Show my 7th semester timetable
Agent: [Shows complete timetable]

User: Sort it by time
Agent: ✅ Sorted your timetable by time:
       [Entries now ordered chronologically]

User: Show only Monday classes
Agent: ✅ Showing only Monday classes:
       [Filtered to Monday entries only]
```

### Example 3: Export Workflow

```
User: Give me timetable for Computer Vision AI-A, Agentic AI AI-A
Agent: [Shows timetable]

User: Export this as Excel
Agent: ✅ **Excel file created successfully!**

       File saved to: `data/timetable_exports/timetable_20251016_143022.xlsx`

       Open it in Microsoft Excel, Google Sheets, or LibreOffice Calc.

User: Also export as iCal for my calendar
Agent: ✅ **iCal file created successfully!**

       File saved to: `data/timetable_exports/timetable_20251016_143045.ics`

       Import this file into:
       - Google Calendar
       - Apple Calendar
       - Outlook
       - Any calendar app that supports .ics files
```

---

## 🔧 Files Modified

1. **`multiagent/agents/timetable_agent.py`**
   - Added `manipulate_timetable` tool (lines 962-1108)
   - Added `export_timetable` tool (lines 1253-1405)
   - Updated tools list to include new tools (lines 1410-1417)
   - Enhanced system prompt with follow-up guidance (lines 1419-1448)
   - Updated workflow section (lines 1450-1490)

---

## ✅ Status

- ✅ **Follow-up queries**: Fully functional with manipulate_timetable
- ✅ **CSV export**: Working (no dependencies)
- ✅ **Excel export**: Working (requires pandas + openpyxl)
- ✅ **iCal export**: Working (requires icalendar + pytz)
- ⏳ **PDF export**: Not yet implemented (suggests alternatives)
- ✅ **Backward compatibility**: All existing functionality preserved
- ✅ **Documentation**: Complete with examples and technical details

---

## 🎓 Key Insights

1. **React agents naturally support follow-ups** - The LLM reasoning enables context-aware responses without explicit memory tools

2. **Structured data in additional_kwargs is crucial** - This enables follow-up tools to access previous results

3. **Graceful degradation for optional dependencies** - Export functionality works with what's available, suggests installations when needed

4. **System prompt is powerful** - Clear workflow guidance helps the agent use tools correctly

5. **No breaking changes needed** - New features added alongside existing ones, maintaining full backward compatibility
