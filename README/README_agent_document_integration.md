# Agent Document Upload Integration - Implementation Guide

## Overview

Enhanced the OBE Agent and Exam Agent to leverage uploaded course documents for more contextual and accurate responses.

## OBE Agent Enhancements

### New Capabilities

**1. Extract CLOs/PLOs from Uploaded Documents**

```python
from multiagent.agents.obe_agent.obe_agent import OBEAgent

agent = OBEAgent()

# Extract outcomes from uploaded course outline
result = agent.extract_outcomes_from_document(
    user_id=1,
    session_id="42",
    outcome_type="both"  # "clo", "plo", or "both"
)

# Returns:
# {
#     "clos": ["CLO 1: ...", "CLO 2: ..."],
#     "plos": ["PLO 1: ...", "PLO 2: ..."],
#     "raw_text": "...",
#     "extracted_text": "..."
# }
```

**2. Improve Existing Outcomes**

```python
# Improve CLOs based on OBE best practices
improved = agent.improve_outcomes(
    outcomes=["Students will learn Python", "Understand algorithms"],
    outcome_type="CLO",
    improvement_focus="clarity and measurability using Bloom's taxonomy"
)

# Returns:
# {
#     "original": [...],
#     "improved_response": "Detailed improvements with rationale",
#     "outcome_type": "CLO"
# }
```

**3. Auto-Extract for Mapping**

```python
# If no CLOs/PLOs provided, automatically extract from documents
mapping = agent.run(
    clos=[],  # Empty - will auto-extract
    plos=[],  # Empty - will auto-extract
    user_id=1,
    session_id="42"
)
```

### Use Cases

1. **Upload course syllabus** → Extract CLOs and PLOs → Generate mapping
2. **Upload course outline** → Extract CLOs → Improve them based on OBE standards
3. **Manual CLOs + uploaded PLOs** → Extract PLOs, use provided CLOs → Map them

### Integration

**Current**: Simple run method

```python
agent.run(clos=["..."], plos=["..."])
```

**Enhanced**: Auto-extraction support

```python
agent.run(clos=[], plos=[], user_id=1, session_id="42")
# Agent checks for uploaded documents and extracts CLOs/PLOs automatically
```

## Exam Agent Enhancements

### New Tool: `search_uploaded_lecture_content`

**Purpose**: Query uploaded lecture slides, notes, and course materials to understand what was actually taught.

**Usage**:

```python
# Tool automatically called by agent when generating exams
# Example internal call:
content = search_uploaded_lecture_content(
    query="machine learning algorithms",
    user_id=1,
    session_id="42"
)
```

### Enhanced Workflow

**Before** (Past exams only):

1. User: "Generate exam for Machine Learning"
2. Agent: Searches past ML exams
3. Agent: Generates generic questions

**After** (Lecture content + Past exams):

1. User uploads lecture slides
2. User: "Generate exam based on my lectures"
3. Agent: Queries uploaded lecture content for topics covered
4. Agent: Searches past exams for question styles
5. Agent: Generates contextual questions based on actual lecture content

### System Prompt Updates

**Faculty Role**:

```
PRIORITY: Always check for uploaded lecture content first
- Use search_uploaded_lecture_content to understand what was taught
- Use search_exam_inspiration for question style ideas
- Generate questions based on ACTUAL lecture content, not generic topics
```

**Student Role**:

```
PRIORITY: Always check for uploaded lecture content first
- Query uploaded materials to create contextual practice questions
- Use past exams for formatting guidance
- Ensure practice exam matches the actual course content
```

### Use Cases

1. **Upload lecture slides** → "Generate final exam" → Questions based on slides
2. **Upload course notes** → "Create practice quiz on week 5 topics" → Targeted questions
3. **Upload multiple lectures** → "Make exam covering all uploaded content" → Comprehensive exam

## Implementation Details

### OBE Agent (`multiagent/agents/obe_agent/obe_agent.py`)

**New Methods**:

- `extract_outcomes_from_document()`: Extract CLOs/PLOs from uploaded syllabus
- `improve_outcomes()`: Improve CLOs/PLOs using OBE best practices
- Enhanced `run()`: Auto-extract if outcomes not provided

**Dependencies**:

```python
from multiagent.memory.retriever_manager import get_session_retriever
```

**RAG Flow**:

1. Get session retriever
2. Query for "learning outcomes", "CLO", "PLO"
3. Retrieve relevant chunks
4. Use LLM to extract structured outcomes
5. Parse and format results

### Exam Agent (`multiagent/agents/exam_react_agent.py`)

**New Tool**:

```python
@tool
def search_uploaded_lecture_content(query: str, user_id: int, session_id: str) -> str:
    """Search uploaded course materials for relevant content"""
    # Get session retriever
    # Query uploaded documents
    # Return top 5 relevant chunks
```

**Tool List Updated**:

```python
tools = [
    search_uploaded_lecture_content,  # NEW
    search_exam_inspiration,
    calculate_exam_marks,
    validate_exam_structure
]
```

**Dependencies**:

```python
from multiagent.memory.retriever_manager import get_session_retriever
```

## Limitations & Workarounds

### Current Limitation: Tool Parameters

LangChain tools receive parameters from LLM, but `user_id` and `session_id` are not part of the user's question.

**Problem**:

```python
@tool
def search_uploaded_lecture_content(query: str, user_id: int, session_id: str) -> str:
    # LLM only provides 'query', not user_id/session_id
```

**Solution Options**:

**Option 1: Pass via State (RECOMMENDED)**

```python
# In supervisor or node, bind state to tool
from functools import partial

# Create bound tool with user context
bound_tool = partial(
    search_uploaded_lecture_content_impl,
    user_id=state["user_id"],
    session_id=state["session_id"]
)
```

**Option 2: Global Context**

```python
# Set context before agent call
from contextvars import ContextVar
current_user_id = ContextVar('user_id')
current_session_id = ContextVar('session_id')

# In tool
user_id = current_user_id.get()
session_id = current_session_id.get()
```

**Option 3: Modify Agent Invocation**

```python
# Pass user context when calling agent
exam_agent.stream_async(
    question,
    session_id=session_id,
    user_id=user_id,  # Add this
    user_role=user_role
)
```

### Recommended Implementation

**Step 1**: Modify agent methods to accept user_id

```python
async def stream_async(
    self,
    question: str,
    session_id: str = "default",
    user_id: int = None,  # Add this
    user_role: str = "student"
):
```

**Step 2**: Store in agent state

```python
self.current_user_id = user_id
self.current_session_id = session_id
```

**Step 3**: Create tool wrapper

```python
def _create_agent(self):
    # Wrapper that uses stored context
    def search_uploaded_content_wrapper(query: str) -> str:
        return search_uploaded_lecture_content(
            query=query,
            user_id=self.current_user_id,
            session_id=self.current_session_id
        )

    tools = [search_uploaded_content_wrapper, ...]
```

## Testing

### Test OBE Agent

```python
# Test extraction
from multiagent.agents.obe_agent.obe_agent import OBEAgent

agent = OBEAgent()

# Upload course syllabus first via API
# Then extract
result = agent.extract_outcomes_from_document(
    user_id=1,
    session_id="test_session"
)

print(f"Found {len(result['clos'])} CLOs")
print(f"Found {len(result['plos'])} PLOs")

# Test improvement
improved = agent.improve_outcomes(
    outcomes=result['clos'],
    outcome_type="CLO",
    improvement_focus="Bloom's taxonomy alignment"
)
print(improved['improved_response'])
```

### Test Exam Agent

```python
# Test with uploaded content
from multiagent.agents.exam_react_agent import exam_react_agent

# Upload lecture slides first via API
# Then generate exam
for chunk in exam_react_agent.stream(
    "Generate a final exam based on my uploaded lecture slides",
    session_id="test_session",
    user_role="faculty"
):
    print(chunk, end="", flush=True)
```

## Next Steps

### Priority 1: Fix Tool Context Issue

- [ ] Modify `stream_async()` to accept `user_id`
- [ ] Store user context in agent instance
- [ ] Create tool wrappers that use stored context
- [ ] Update supervisor to pass `user_id` when calling agents

### Priority 2: Update Supervisor/Nodes

- [ ] Extract `user_id` from state in supervisor
- [ ] Pass to exam agent in `exam_node_runner()`
- [ ] Pass to OBE agent (when integrated into graph)

### Priority 3: Documentation

- [ ] Update API docs with upload + agent workflow
- [ ] Add example requests showing upload → generate pattern
- [ ] Document best practices for course material uploads

### Priority 4: UI Updates

- [ ] Show "Analyzing uploaded materials..." message
- [ ] Display which documents were used for generation
- [ ] Allow users to select which uploads to use

## Example Workflows

### Workflow 1: Generate Exam from Lectures

```bash
# Step 1: Upload lectures
curl -X POST http://localhost:8000/api/v1/chats/42/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@lecture_1.pdf"

curl -X POST http://localhost:8000/api/v1/chats/42/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@lecture_2.pdf"

# Step 2: Generate exam
curl -X POST http://localhost:8000/api/v1/multiagent/stream \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "question": "Generate a final exam covering all uploaded lectures",
    "session_id": 42
  }'

# Agent will:
# 1. Query uploaded lectures for topics
# 2. Search past exams for question styles
# 3. Generate contextual exam questions
```

### Workflow 2: Extract and Map CLOs

```bash
# Step 1: Upload course syllabus
curl -X POST http://localhost:8000/api/v1/chats/42/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@syllabus.pdf"

# Step 2: Request CLO-PLO mapping
curl -X POST http://localhost:8000/api/v1/multiagent/stream \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "question": "Extract CLOs and PLOs from the syllabus and create a mapping",
    "session_id": 42
  }'

# OBE Agent will:
# 1. Query uploaded syllabus
# 2. Extract CLOs and PLOs
# 3. Generate mapping table
```

### Workflow 3: Improve Outcomes

```python
# After extracting from uploaded syllabus
agent = OBEAgent()

# Extract first
extraction = agent.extract_outcomes_from_document(user_id=1, session_id="42")

# Then improve
improved = agent.improve_outcomes(
    outcomes=extraction['clos'],
    outcome_type="CLO",
    improvement_focus="Make them more measurable and specific"
)
```

## Benefits

### For Students

- ✅ Practice exams tailored to actual lecture content
- ✅ Questions based on what was taught, not generic topics
- ✅ Better exam preparation

### For Faculty

- ✅ Generate exams from lecture materials automatically
- ✅ Ensure alignment between lectures and assessments
- ✅ Extract learning outcomes from existing syllabi
- ✅ Improve outcomes based on OBE best practices

### For System

- ✅ Context-aware responses
- ✅ Leverages uploaded content
- ✅ More accurate and relevant outputs
- ✅ Reduced hallucination (grounds responses in actual materials)

---

**Status**: Core functionality implemented, tool context binding pending  
**Next**: Fix tool parameter passing for user_id/session_id  
**Priority**: HIGH - Required for production use
