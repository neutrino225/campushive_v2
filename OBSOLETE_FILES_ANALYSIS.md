# Obsolete Files Analysis & Cleanup Recommendations

## Files to Remove (Obsolete/Unused)

### 1. Legacy Supervisor Files

#### `/multiagent/legacy/supervisor_classic_backup.py`

- **Status**: ❌ Obsolete
- **Reason**: Backup of old delegation pattern before migration
- **Action**: Keep in legacy folder for reference, but not loaded by system

#### `/multiagent/legacy/supervisor_delegation.py`

- **Status**: ❌ Obsolete
- **Reason**: Old delegation implementation, replaced by Command-based pattern
- **Action**: Keep in legacy folder for reference

#### `/multiagent/graph/main_supervisor.py`

- **Status**: ❌ UNUSED - Can be deleted
- **Reason**: Not imported anywhere, superseded by `planning_supervisor.py`
- **Search Results**: No imports found in codebase
- **Action**: **DELETE** - No longer needed

### 2. Web Search Agent

#### `/multiagent/agents/web_search_agent.py`

- **Status**: ⚠️ Currently UNUSED but keep for future
- **Reason**: Removed from planning_supervisor to prevent hallucinations
- **Usage**: Only referenced in `test_planning_supervisor.py`
- **Action**: **KEEP** - May be useful for future external info queries with proper constraints
- **Note**: If re-added, needs very explicit prompt restrictions

### 3. Test Files (Root Directory)

#### `/test_simple_context.py`

- **Status**: ⚠️ Development test file
- **Reason**: Ad-hoc testing during development
- **Action**: Move to `/tests/` or delete if obsolete

#### `/test_context_memory.py`

- **Status**: ⚠️ Development test file
- **Reason**: Memory system testing
- **Action**: Move to `/tests/agent_tests/` or integrate into proper tests

#### `/test_planning_supervisor.py`

- **Status**: ⚠️ Development test file
- **Reason**: Planning supervisor testing
- **Action**: Move to `/tests/agent_tests/` or update imports

### 4. Utility Scripts

#### `/save_images.py`

- **Status**: ❓ Unknown purpose
- **Action**: Check if used, otherwise delete

#### `/run_assistant.py`

- **Status**: ✅ Keep
- **Reason**: CLI interface for testing assistant
- **Action**: Keep as development utility

## Files to Keep (Active)

### Core System Files

✅ `/config.py` - LLM and embeddings configuration  
✅ `/vector_store_manager.py` - Vector store management  
✅ `/utils.py` - General utilities  
✅ `/paths.py` - Path management

### Multiagent Core

✅ `/multiagent/graph/supervisor.py` - Main supervisor (legacy hierarchical + planning integration)  
✅ `/multiagent/graph/planning_supervisor.py` - Planning-based supervisor with ReAct  
✅ `/multiagent/graph/student_supervisor.py` - Student domain router  
✅ `/multiagent/graph/faculty_supervisor.py` - Faculty domain router  
✅ `/multiagent/graph/planning_state.py` - Planning state TypedDict  
✅ `/multiagent/graph/planning_tools.py` - Tools for planning supervisor

### Agents

✅ `/multiagent/agents/general_agent.py` - General university info  
✅ `/multiagent/agents/degree_advisor_agent.py` - Degree programs and courses  
✅ `/multiagent/agents/timetable_agent.py` - Course schedules  
✅ `/multiagent/agents/faculty_react_agent.py` - Faculty information  
✅ `/multiagent/agents/exam_react_agent.py` - Exam generation  
✅ `/multiagent/agents/obe_agent/` - OBE/CLO-PLO mappings  
⚠️ `/multiagent/agents/web_search_agent.py` - Keep for future use  
❌ `/multiagent/agents/student_agent.py` - Check if obsolete (replaced by wrappers?)

### Memory & State

✅ `/multiagent/memory/manager.py` - Conversation memory management  
✅ `/multiagent/routing/classifiers.py` - Intent classification

### API & Database

✅ `/app/main.py` - FastAPI application  
✅ `/app/routers/` - All API routes  
✅ `/app/database/` - Database models and connection  
✅ `/app/auth/` - Authentication and security  
✅ `/app/schemas/` - Pydantic schemas

### Scripts

✅ `/scripts/init_db.py` - Database initialization  
✅ `/scripts/create_admin.py` - Admin user creation  
✅ `/scripts/*_cli.py` - CLI testing utilities  
✅ `/scrapers/*.py` - Data scraping scripts

### Tests

✅ `/tests/api_tests/` - API endpoint tests  
✅ `/tests/agent_tests/` - Agent functionality tests  
✅ `/tests/conftest.py` - Pytest configuration

## Cleanup Actions

### Immediate (Can Delete Now)

```bash
# 1. Delete unused main_supervisor
rm multiagent/graph/main_supervisor.py

# 2. Move test files from root to tests/
mv test_simple_context.py tests/development/
mv test_context_memory.py tests/development/
mv test_planning_supervisor.py tests/agent_tests/

# 3. Check and remove save_images.py if not used
# Review the file first
cat save_images.py
# If obsolete: rm save_images.py
```

### Review Required

```bash
# 1. Check if student_agent.py is obsolete
grep -r "student_agent" --include="*.py" .

# 2. Verify web_search_agent usage
grep -r "web_search_agent" --include="*.py" .
```

### Legacy Files (Keep for Reference)

These are intentionally kept in `/multiagent/legacy/` for historical reference:

- `supervisor_classic_backup.py`
- `supervisor_delegation.py`

## Summary

### Delete Immediately

1. ❌ `/multiagent/graph/main_supervisor.py` - Completely unused

### Move to Tests Directory

2. ⚠️ `/test_simple_context.py` → `/tests/development/`
3. ⚠️ `/test_context_memory.py` → `/tests/development/`
4. ⚠️ `/test_planning_supervisor.py` → `/tests/agent_tests/`

### Review & Decide

5. ❓ `/save_images.py` - Unknown purpose
6. ❓ `/multiagent/agents/student_agent.py` - May be obsolete

### Keep (Currently Inactive but Useful)

7. ⚠️ `/multiagent/agents/web_search_agent.py` - Future use with proper constraints
8. ✅ `/multiagent/legacy/*` - Historical reference

## Post-Cleanup File Structure

```
campushive_v2/
├── config.py ✅
├── vector_store_manager.py ✅
├── utils.py ✅
├── paths.py ✅
├── run_assistant.py ✅
├── app/ ✅ (All active)
├── data/ ✅
├── multiagent/
│   ├── agents/
│   │   ├── general_agent.py ✅
│   │   ├── degree_advisor_agent.py ✅
│   │   ├── timetable_agent.py ✅
│   │   ├── faculty_react_agent.py ✅
│   │   ├── exam_react_agent.py ✅
│   │   ├── web_search_agent.py ⚠️ (inactive, keep for future)
│   │   └── obe_agent/ ✅
│   ├── graph/
│   │   ├── supervisor.py ✅
│   │   ├── planning_supervisor.py ✅
│   │   ├── student_supervisor.py ✅
│   │   ├── faculty_supervisor.py ✅
│   │   ├── planning_state.py ✅
│   │   └── planning_tools.py ✅
│   ├── memory/ ✅
│   ├── routing/ ✅
│   ├── prompts/ ✅
│   └── legacy/ ✅ (reference only)
├── scripts/ ✅ (All active)
├── scrapers/ ✅ (All active)
└── tests/
    ├── api_tests/ ✅
    ├── agent_tests/ ✅
    └── development/ (New - for ad-hoc test files)
```

## Files Count

- **Active & Required**: ~150 files
- **Legacy (Reference)**: 2 files
- **To Delete**: 1 file
- **To Move**: 3 files
- **To Review**: 2 files
