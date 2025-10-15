import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Tuple
from langchain_core.messages import AIMessage

# Add the root directory to the Python path so we can import from root modules
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langchain_core.messages import HumanMessage, SystemMessage
from langchain.prompts import PromptTemplate
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from config import embeddings, llm, small_llm
from vector_store_manager import VectorStoreManager, VectorStoreType
from multiagent.prompts.degree_advisor import degree_advisor_prompt
import textwrap


class DegreeVectorStore:
    """Thin wrapper to get a retriever for degree programs."""

    def __init__(self):
        self.manager = VectorStoreManager(embeddings=embeddings)

    def get_retriever(self, k: int = 15):
        # The manager already returns an ensemble retriever when requested
        return self.manager.get_retriever(VectorStoreType.DEGREE_PROGRAMS, use_ensemble=True)


class DegreeCatalog:
    """Enhanced catalog for degree programs with intelligent parsing and indexing."""

    def __init__(self, json_path: Optional[Path] = None):
        self.path = json_path or (root_dir / "data" / "degree_programs" / "degree_programs.json")
        self._items: List[Dict[str, Any]] = []
        self._index_by_title: Dict[str, Dict[str, Any]] = {}
        self._index_by_level: Dict[str, List[Dict[str, Any]]] = {}
        self._index_by_field: Dict[str, List[Dict[str, Any]]] = {}
        self._load()

    def _load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._items = data if isinstance(data, list) else data.get("programs", [])
                
                # Build indexes
                for item in self._items:
                    # Title index
                    title = str(item.get("title", "")).strip().lower()
                    if title:
                        self._index_by_title[title] = item
                    
                    # Level index
                    level = self._extract_level(item.get("title", ""))
                    if level:
                        if level not in self._index_by_level:
                            self._index_by_level[level] = []
                        self._index_by_level[level].append(item)
                    
                    # Field index
                    field = self._extract_field(item.get("title", ""))
                    if field:
                        if field not in self._index_by_field:
                            self._index_by_field[field] = []
                        self._index_by_field[field].append(item)
        except Exception as e:
            print(f"Error loading degree catalog: {e}")
            self._items = []
            self._index_by_title = {}
            self._index_by_level = {}
            self._index_by_field = {}

    def _extract_level(self, title: str) -> str:
        """Extract degree level from title."""
        title_lower = title.lower()
        if "bachelor" in title_lower or "bs" in title_lower or "b.s." in title_lower:
            return "bachelor"
        elif "master" in title_lower or "ms" in title_lower or "m.s." in title_lower:
            return "master"
        elif "phd" in title_lower or "ph.d." in title_lower or "doctorate" in title_lower:
            return "phd"
        return ""

    def _extract_field(self, title: str) -> str:
        """Extract field of study from title."""
        # Extract text in parentheses (e.g., "Bachelor of Science (Computer Science)")
        match = re.search(r'\(([^)]+)\)', title)
        if match:
            return match.group(1).strip().lower()
        
        # Common field keywords
        title_lower = title.lower()
        if "computer science" in title_lower or "cs" in title_lower:
            return "computer science"
        elif "software engineering" in title_lower or "se" in title_lower:
            return "software engineering"
        elif "artificial intelligence" in title_lower or "ai" in title_lower:
            return "artificial intelligence"
        elif "data science" in title_lower or "ds" in title_lower:
            return "data science"
        elif "cybersecurity" in title_lower or "cyber" in title_lower:
            return "cybersecurity"
        elif "business" in title_lower:
            return "business"
        elif "accounting" in title_lower or "finance" in title_lower:
            return "accounting and finance"
        elif "analytics" in title_lower:
            return "business analytics"
        return ""

    def by_field(self, field: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get programs by field with fuzzy matching."""
        field_lower = field.strip().lower()
        if not field_lower:
            return []
        
        results = []
        # Direct field match
        if field_lower in self._index_by_field:
            results.extend(self._index_by_field[field_lower])
        
        # Partial field match
        for f, programs in self._index_by_field.items():
            if field_lower in f and programs[0] not in results:
                results.extend(programs)
        
        # Also search in titles
        for item in self._items:
            if field_lower in str(item.get("title", "")).lower() and item not in results:
                results.append(item)
        
        return results[:limit]

    def by_level(self, level: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Get programs by level with normalization."""
        level_lower = level.strip().lower()
        if not level_lower:
            return []
        
        # Normalize level names
        level_mapping = {
            "bs": "bachelor", "b.s.": "bachelor", "bachelor's": "bachelor",
            "ms": "master", "m.s.": "master", "master's": "master",
            "phd": "phd", "ph.d.": "phd", "doctorate": "phd",
            "undergraduate": "bachelor", "graduate": "master"
        }
        
        normalized_level = level_mapping.get(level_lower, level_lower)
        
        results = []
        if normalized_level in self._index_by_level:
            results.extend(self._index_by_level[normalized_level])
        
        # Also search in titles for exact matches
        for item in self._items:
            if level_lower in str(item.get("title", "")).lower() and item not in results:
                results.append(item)
        
        return results[:limit]

    def details(self, title: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a program."""
        title_lower = title.strip().lower()
        if not title_lower:
            return None
        
        # Exact match
        if title_lower in self._index_by_title:
            return self._index_by_title[title_lower]
        
        # Partial match
        for t, program in self._index_by_title.items():
            if title_lower in t or t in title_lower:
                return program
        
        return None

    def search(self, query: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Search programs by query with relevance ranking."""
        query_lower = query.strip().lower()
        if not query_lower:
            return []
        
        scored_hits = []
        for item in self._items:
            score = 0
            title = str(item.get("title", "")).lower()
            
            # Exact title match
            if query_lower == title:
                score += 100
            elif query_lower in title:
                score += 50
            
            # Field match
            field = self._extract_field(item.get("title", ""))
            if query_lower in field:
                score += 30
            
            # Content match
            content = " ".join([
                str(item.get("career_opportunities", "")),
                str(item.get("vision", "")),
                str(item.get("mission", "")),
            ]).lower()
            
            if query_lower in content:
                score += 10
            
            if score > 0:
                scored_hits.append((score, item))
        
        # Sort by score
        scored_hits.sort(key=lambda x: x[0], reverse=True)
        return [item for score, item in scored_hits[:limit]]

    def get_semester_courses(self, title: str, semester: int) -> List[Dict[str, Any]]:
        """Get courses for a specific semester."""
        program = self.details(title)
        if not program or "semesters" not in program:
            return []
        
        semester_key = f"semester_{semester}"
        return program["semesters"].get(semester_key, [])


class UserPreferenceCollector:
    """Collects and manages user preferences for intelligent recommendations."""

    def __init__(self):
        self.preferences = {
            "interests": [],
            "field": None,
            "level": None,
            "career_goals": [],
            "constraints": [],
            "current_student": None,
            "current_program": None,
            "current_semester": None,
        }
        self.conversation_stage = "initial"

    def update(self, key: str, value: Any) -> str:
        """Update a preference value."""
        if key == "interests" and isinstance(value, list):
            self.preferences["interests"].extend([v for v in value if v not in self.preferences["interests"]])
        elif key == "career_goals" and isinstance(value, list):
            self.preferences["career_goals"].extend([v for v in value if v not in self.preferences["career_goals"]])
        elif key == "constraints" and isinstance(value, list):
            self.preferences["constraints"].extend([v for v in value if v not in self.preferences["constraints"]])
        else:
            self.preferences[key] = value
        return f"Updated {key}: {value}"

    def add_interest(self, interest: str) -> str:
        """Add an interest to the list."""
        if interest not in self.preferences["interests"]:
            self.preferences["interests"].append(interest)
            return f"Added '{interest}' to your interests."
        return f"'{interest}' is already noted."

    def set_student_status(self, is_current: bool, program: str = None, semester: int = None) -> str:
        """Set whether user is a current student."""
        self.preferences["current_student"] = is_current
        if is_current:
            if program:
                self.preferences["current_program"] = program
            if semester:
                self.preferences["current_semester"] = semester
            self.conversation_stage = "current_student"
            return f"I understand you're a current student{' in ' + program if program else ''}{' (Semester ' + str(semester) + ')' if semester else ''}."
        else:
            self.conversation_stage = "prospective_student"
            return "I understand you're a prospective student. I'll help you find the right program."

    def should_ask_clarifying_question(self) -> bool:
        """Determine if we need more information."""
        if self.preferences["current_student"] is None:
            return True
        
        if self.preferences["current_student"]:
            # For current students, we need their program
            return self.preferences["current_program"] is None
        else:
            # For prospective students, we need interests and level
            return not self.preferences["interests"] or not self.preferences["level"]

    def get_next_question(self) -> Optional[str]:
        """Get the next clarifying question to ask."""
        if self.preferences["current_student"] is None:
            return "Are you a current student at FAST-NU Islamabad, or are you a prospective student looking to apply?"
        
        if self.preferences["current_student"]:
            if not self.preferences["current_program"]:
                return "Which program are you currently enrolled in?"
            if not self.preferences["current_semester"]:
                return "Which semester are you currently in?"
            return None
        else:
            if not self.preferences["interests"]:
                return "What are your main academic interests or areas you'd like to study?"
            if not self.preferences["level"]:
                return "What degree level are you looking for? (Bachelor's/BS, Master's/MS, or PhD)"
            if not self.preferences["career_goals"]:
                return "What are your career goals after graduation?"
            return None


class DegreeMatcher:
    """Intelligent matching between user preferences and degree programs."""

    def __init__(self, catalog: DegreeCatalog):
        self.catalog = catalog

    def calculate_score(self, program: Dict[str, Any], preferences: Dict[str, Any]) -> Tuple[int, List[str]]:
        """Calculate compatibility score between program and preferences."""
        score = 0
        reasons = []
        
        title = program.get("title", "").lower()
        
        # Level matching (HIGHEST priority - must match if specified)
        if preferences.get("level"):
            level_pref = preferences["level"].lower()
            level_keywords = {
                "bachelor": ["bachelor", "bs", "b.s."],
                "master": ["master", "ms", "m.s.", "mba"],
                "phd": ["phd", "ph.d.", "doctorate"]
            }
            
            level_match = False
            for keyword in level_keywords.get(level_pref, [level_pref]):
                if keyword in title:
                    level_match = True
                    break
            
            if level_match:
                score += 100  # Very high weight for correct level
                reasons.append(f"Matches your {preferences['level']}-level goal")
            else:
                # Penalize wrong level
                score -= 50
                return score, reasons  # Early return if level doesn't match
        
        # Interest matching (high weight)
        for interest in preferences.get("interests", []):
            if interest.lower() in title or interest.lower() in str(program.get("career_opportunities", "")).lower():
                score += 30
                reasons.append(f"Matches your interest in {interest}")
        
        # Field matching
        if preferences.get("field"):
            field_in_title = preferences["field"].lower() in title
            if field_in_title:
                score += 25
                reasons.append(f"Matches your field preference: {preferences['field']}")
        
        # Career goals matching
        career_opps = str(program.get("career_opportunities", "")).lower()
        for goal in preferences.get("career_goals", []):
            if goal.lower() in career_opps:
                score += 15
                reasons.append(f"Aligns with your career goal: {goal}")
        
        # Background relevance (if they completed a program)
        if preferences.get("completed_program"):
            completed = preferences["completed_program"].lower()
            # Give bonus if program builds on their background
            if any(keyword in completed for keyword in ["ai", "artificial intelligence", "computer", "data"]):
                if any(keyword in title for keyword in ["analytics", "data", "ai", "machine learning", "technology"]):
                    score += 20
                    reasons.append("Builds on your technical background")
        
        return score, reasons

    def find_best_matches(self, preferences: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
        """Find the best matching programs."""
        candidates = []
        
        # Get candidates from catalog
        if preferences.get("field"):
            candidates.extend(self.catalog.by_field(preferences["field"], limit=20))
        
        if preferences.get("level"):
            candidates.extend(self.catalog.by_level(preferences["level"], limit=20))
        
        for interest in preferences.get("interests", []):
            candidates.extend(self.catalog.search(interest, limit=10))
        
        # Remove duplicates
        unique_candidates = {p.get("title"): p for p in candidates if p.get("title")}
        
        # Score all candidates
        scored_programs = []
        for title, program in unique_candidates.items():
            score, reasons = self.calculate_score(program, preferences)
            if score > 0:
                scored_programs.append({
                    "program": program,
                    "score": score,
                    "reasons": reasons
                })
        
        # Sort by score
        scored_programs.sort(key=lambda x: x["score"], reverse=True)
        return scored_programs[:limit]


def _format_program_line(p: Dict[str, Any]) -> str:
    """Format a program for list display."""
    title = p.get("title", "Unknown Title")
    
    # Calculate total semesters and credits
    semesters = len(p.get("semesters", {}))
    total_credits = 0
    for sem_courses in p.get("semesters", {}).values():
        for course in sem_courses:
            credit_str = course.get("credit_hours", "0+0")
            try:
                # Parse "3+1" format
                parts = credit_str.replace("NC+", "0+").split("+")
                total_credits += sum(int(x) for x in parts if x.isdigit())
            except:
                pass
    
    tail = []
    if semesters:
        tail.append(f"{semesters} semesters")
    if total_credits:
        tail.append(f"{total_credits} credits")
    
    tail_str = f" ({', '.join(tail)})" if tail else ""
    return f"- {title}{tail_str}"


def _format_details(p: Dict[str, Any]) -> str:
    """Format detailed program information."""
    if not p:
        return "No details available."
    
    parts = []
    parts.append(f"**{p.get('title', 'N/A')}**\n")
    
    if p.get("eligibility"):
        parts.append(f"**Eligibility:** {p.get('eligibility')}\n")
    
    if p.get("vision"):
        parts.append(f"**Vision:** {p.get('vision')}\n")
    
    if p.get("mission"):
        parts.append(f"**Mission:** {p.get('mission')}\n")
    
    if p.get("career_opportunities"):
        parts.append(f"**Career Opportunities:** {p.get('career_opportunities')}\n")
    
    # Program structure
    semesters = p.get("semesters", {})
    if semesters:
        total_semesters = len(semesters)
        total_credits = 0
        for sem_courses in semesters.values():
            for course in sem_courses:
                credit_str = course.get("credit_hours", "0+0")
                try:
                    parts_list = credit_str.replace("NC+", "0+").split("+")
                    total_credits += sum(int(x) for x in parts_list if x.isdigit())
                except:
                    pass
        
        parts.append(f"**Program Structure:**")
        parts.append(f"- Total Semesters: {total_semesters}")
        parts.append(f"- Total Credit Hours: {total_credits}\n")
    
    # PEOs
    if p.get("peos"):
        parts.append("**Program Educational Objectives:**")
        for i, peo in enumerate(p.get("peos", []), 1):
            parts.append(f"{i}. {peo}")
        parts.append("")
    
    # URL
    if p.get("url"):
        parts.append(f"**More Information:** {p.get('url')}")
    
    return "\n".join(parts)


# ---------------- Tool-enabled LangGraph Agent ---------------- #

# ============= GLOBAL TOOL INSTANCES =============

_CATALOG_INSTANCE: Optional[DegreeCatalog] = None
_RETRIEVER_INSTANCE = None


def _get_catalog() -> DegreeCatalog:
    global _CATALOG_INSTANCE
    if _CATALOG_INSTANCE is None:
        _CATALOG_INSTANCE = DegreeCatalog()
    return _CATALOG_INSTANCE


def _get_retriever():
    global _RETRIEVER_INSTANCE
    if _RETRIEVER_INSTANCE is None:
        _RETRIEVER_INSTANCE = DegreeVectorStore().get_retriever(k=20)
    return _RETRIEVER_INSTANCE


# ============= TOOL DEFINITIONS =============

@tool
def list_programs_by_field(field: str) -> str:
    """List all degree programs in a specific field.
    
    Args:
        field: The field of study to search for (e.g., 'Computer Science', 'AI', 'Business')
    
    Returns:
        Formatted list of degree programs in that field
    """
    catalog = _get_catalog()
    retriever = _get_retriever()
    
    # JSON first
    json_hits = catalog.by_field(field, limit=20)
    # vector assist
    docs = retriever.invoke(f"degree programs in {field}")
    seen = set([str(p.get("title", "")).lower() for p in json_hits])
    for d in docs:
        t = str(d.metadata.get("title", "")).strip()
        if t and t.lower() not in seen:
            json_hits.append({
                "title": t,
                "level": d.metadata.get("level", ""),
                "field": d.metadata.get("field", ""),
                "duration_years": d.metadata.get("duration_years", ""),
                "total_credit_hours": d.metadata.get("total_credit_hours", ""),
            })
            seen.add(t.lower())
    if not json_hits:
        return f"No degree programs found for field '{field}'. Try a broader term."
    return f"Degree programs in {field}:\n" + "\n".join(_format_program_line(p) for p in json_hits[:15])


@tool
def list_programs_by_level(level: str) -> str:
    """List all degree programs at a specific level.
    
    Args:
        level: The degree level (e.g., 'Bachelor', 'Master', 'PhD', 'BS', 'MS')
    
    Returns:
        Formatted list of degree programs at that level
    """
    catalog = _get_catalog()
    retriever = _get_retriever()
    
    json_hits = catalog.by_level(level, limit=30)
    docs = retriever.invoke(f"{level} degree programs")
    seen = set([str(p.get("title", "")).lower() for p in json_hits])
    for d in docs:
        t = str(d.metadata.get("title", "")).strip()
        if t and t.lower() not in seen and level.lower() in str(d.metadata.get("level", "")).lower():
            json_hits.append({
                "title": t,
                "level": d.metadata.get("level", ""),
                "field": d.metadata.get("field", ""),
                "duration_years": d.metadata.get("duration_years", ""),
                "total_credit_hours": d.metadata.get("total_credit_hours", ""),
            })
            seen.add(t.lower())
    if not json_hits:
        return f"No {level} degree programs found."
    return f"{level} degree programs:\n" + "\n".join(_format_program_line(p) for p in json_hits[:20])


@tool
def get_program_details(program_title: str) -> str:
    """Get comprehensive details about a specific degree program.
    
    Args:
        program_title: The exact or partial program title
    
    Returns:
        Detailed information about the program
    """
    catalog = _get_catalog()
    retriever = _get_retriever()
    
    # JSON exact/fuzzy
    p = catalog.details(program_title)
    if p:
        return _format_details(p)
    # semantic fallback
    docs = retriever.invoke(f"{program_title} program details")
    for d in docs:
        if program_title.lower() in str(d.metadata.get("title", "")).lower():
            return d.page_content
    return docs[0].page_content if docs else f"No detailed information found for {program_title}."


@tool
def compare_programs(programs_text: str) -> str:
    """Compare two degree programs side-by-side.
    
    Args:
        programs_text: Two program names separated by 'vs', '|', or ',' (e.g., 'BS Computer Science vs BS Software Engineering')
    
    Returns:
        Side-by-side comparison of the two programs
    """
    catalog = _get_catalog()
    retriever = _get_retriever()
    
    raw = (programs_text or "").strip()
    if " vs " in raw.lower():
        a, b = raw.lower().split(" vs ", 1)
    elif "|" in raw:
        a, b = raw.split("|", 1)
    else:
        parts = raw.split(",")
        if len(parts) >= 2:
            a, b = parts[0], parts[1]
        else:
            return "Please provide two program names, e.g., 'BS Computer Science vs BS Software Engineering'."
    a = a.strip(); b = b.strip()

    # Gather details (JSON first, then vector fallback)
    da = catalog.details(a)
    db = catalog.details(b)
    if not da:
        docs_a = retriever.invoke(f"{a} program details")
        if docs_a:
            da = {
                "title": docs_a[0].metadata.get("title", a),
                "level": docs_a[0].metadata.get("level", ""),
                "field": docs_a[0].metadata.get("field", ""),
                "duration_years": docs_a[0].metadata.get("duration_years", ""),
                "total_credit_hours": docs_a[0].metadata.get("total_credit_hours", ""),
                "summary": docs_a[0].page_content,
            }
    if not db:
        docs_b = retriever.invoke(f"{b} program details")
        if docs_b:
            db = {
                "title": docs_b[0].metadata.get("title", b),
                "level": docs_b[0].metadata.get("level", ""),
                "field": docs_b[0].metadata.get("field", ""),
                "duration_years": docs_b[0].metadata.get("duration_years", ""),
                "total_credit_hours": docs_b[0].metadata.get("total_credit_hours", ""),
                "summary": docs_b[0].page_content,
            }

    if not da or not db:
        return f"Could not find sufficient information to compare {a} and {b}."

    lines = [
        f"COMPARISON: {da.get('title', a)} vs {db.get('title', b)}",
        "",
        f"Program 1: {da.get('title', a)}",
        f"Level: {da.get('level', 'N/A')}",
        f"Duration: {da.get('duration_years', 'N/A')} years",
        f"Credit Hours: {da.get('total_credit_hours', 'N/A')}",
        "",
        f"Program 2: {db.get('title', b)}",
        f"Level: {db.get('level', 'N/A')}",
        f"Duration: {db.get('duration_years', 'N/A')} years",
        f"Credit Hours: {db.get('total_credit_hours', 'N/A')}",
    ]
    if da.get("summary") or db.get("summary"):
        lines += [
            "",
            "Key Details:",
            f"- {da.get('title', a)}: {da.get('summary', '')[:600]}",
            f"- {db.get('title', b)}: {db.get('summary', '')[:600]}",
        ]
    return "\n".join(lines)


@tool
def get_semester_courses(program_and_semester: str) -> str:
    """Get list of courses for a specific semester of a program.
    
    Args:
        program_and_semester: Program name and semester number separated by comma (e.g., 'BS Computer Science, 3' or 'BS AI, 5')
    
    Returns:
        List of courses for that semester with credit hours
    """
    catalog = _get_catalog()
    
    # Use small_llm to parse the input
    parse_prompt = f"""Extract the program name and semester number from this text: "{program_and_semester}"

Return ONLY a JSON object with two keys:
{{
  "program": "program name or abbreviation",
  "semester": semester_number
}}

IMPORTANT: Keep abbreviations as-is (e.g., "BS", "MS", "AI", "CS"). Do NOT expand them.

Examples:
Input: "BS Computer Science, 3" -> {{"program": "BS Computer Science", "semester": 3}}
Input: "List courses for BS AI semester 5" -> {{"program": "BS AI", "semester": 5}}
Input: "List all semester wise courses for BS AI" -> {{"program": "BS AI", "semester": 1}}
Input: "What are the courses in semester 2 of BS Software Engineering?" -> {{"program": "BS Software Engineering", "semester": 2}}
Input: "6th semester of BS AI" -> {{"program": "BS AI", "semester": 6}}

Note: If no specific semester is mentioned but the user asks for "all semesters" or "semester wise", default to semester 1.

Now parse: "{program_and_semester}"
Return ONLY the JSON object, nothing else."""

    try:
        response = small_llm.invoke([HumanMessage(content=parse_prompt)])
        content = response.content.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{[^}]+\}', content)
        if json_match:
            parsed = json.loads(json_match.group())
            program_title = parsed.get("program", "").strip()
            semester = int(parsed.get("semester", 0))
        else:
            # Fallback to simple parsing
            parts = program_and_semester.split(",")
            if len(parts) < 2:
                return "Please provide both program name and semester number (e.g., 'BS Computer Science, 3')"
            program_title = parts[0].strip()
            semester = int(parts[1].strip())
    except Exception as e:
        # Fallback to simple parsing
        parts = program_and_semester.split(",")
        if len(parts) < 2:
            return "Please provide both program name and semester number (e.g., 'BS Computer Science, 3')"
        program_title = parts[0].strip()
        try:
            semester = int(parts[1].strip())
        except ValueError:
            return "Please provide a valid semester number."
    
    courses = catalog.get_semester_courses(program_title, semester)
    if not courses:
        # Try searching for the program with intelligent normalization and fuzzy matching
        all_programs = list(catalog._index_by_title.keys())
        
        # Normalize query: expand common abbreviations
        normalized_query = program_title.lower()
        expansions = {
            r'\bbs\b': 'bachelor of science',
            r'\bms\b': 'master of science',
            r'\bphd\b': 'doctor of philosophy',
            r'\bai\b': 'artificial intelligence',
            r'\bcs\b': 'computer science',
            r'\bse\b': 'software engineering',
            r'\bds\b': 'data science',
        }
        for abbr, full in expansions.items():
            normalized_query = re.sub(abbr, full, normalized_query)
        
        # Try exact match first with normalized query
        for prog_key in all_programs:
            if normalized_query in prog_key or prog_key in normalized_query:
                program_title = prog_key
                courses = catalog.get_semester_courses(program_title, semester)
                if courses:
                    break
        
        # If still no match, try fuzzy matching
        if not courses:
            from difflib import get_close_matches
            matches = get_close_matches(normalized_query, all_programs, n=3, cutoff=0.5)
            # Prefer bachelor over master for ambiguous matches
            for match in matches:
                if ('bachelor' in normalized_query and 'bachelor' in match) or \
                   ('master' in normalized_query and 'master' in match) or \
                   (not any(x in normalized_query for x in ['bachelor', 'master'])):
                    program_title = match
                    courses = catalog.get_semester_courses(program_title, semester)
                    if courses:
                        break
    
    if not courses:
        return f"No courses found for {program_title}, Semester {semester}. Please check the program name and semester number."
    
    lines = [f"**{program_title} - Semester {semester} Courses:**\n"]
    for course in courses:
        code = course.get("code", "")
        name = course.get("name", "")
        credits = course.get("credit_hours", "")
        lines.append(f"- {code}: {name} ({credits} credit hours)")
    
    return "\n".join(lines)


@tool
def get_all_semester_courses(program_name: str) -> str:
    """Get complete semester-wise course breakdown for a program (all semesters).
    
    Args:
        program_name: Program name or abbreviation (e.g., 'BS AI', 'BS Computer Science')
    
    Returns:
        Complete list of all courses for all semesters of the program
    """
    catalog = _get_catalog()
    
    # Normalize the program name
    normalized_query = program_name.lower()
    expansions = {
        r'\bbs\b': 'bachelor of science',
        r'\bms\b': 'master of science',
        r'\bphd\b': 'doctor of philosophy',
        r'\bai\b': 'artificial intelligence',
        r'\bcs\b': 'computer science',
        r'\bse\b': 'software engineering',
        r'\bds\b': 'data science',
    }
    for abbr, full in expansions.items():
        normalized_query = re.sub(abbr, full, normalized_query)
    
    # Find the program
    program = None
    all_programs = list(catalog._index_by_title.keys())
    
    # Try exact match first
    for prog_key in all_programs:
        if normalized_query in prog_key or prog_key in normalized_query:
            program = catalog._index_by_title[prog_key]
            break
    
    # Try fuzzy matching if exact match fails
    if not program:
        from difflib import get_close_matches
        matches = get_close_matches(normalized_query, all_programs, n=3, cutoff=0.5)
        for match in matches:
            if ('bachelor' in normalized_query and 'bachelor' in match) or \
               ('master' in normalized_query and 'master' in match) or \
               (not any(x in normalized_query for x in ['bachelor', 'master'])):
                program = catalog._index_by_title[match]
                break
    
    if not program or "semesters" not in program:
        return f"No program found matching '{program_name}'. Please check the program name."
    
    # Build complete semester-wise breakdown
    title = program.get("title", program_name)
    lines = [f"**{title} - Complete Semester-Wise Course Breakdown:**\n"]
    
    semesters = program.get("semesters", {})
    semester_nums = sorted([int(k.replace("semester_", "")) for k in semesters.keys() if k.startswith("semester_")])
    
    for sem_num in semester_nums:
        sem_key = f"semester_{sem_num}"
        courses = semesters.get(sem_key, [])
        if courses:
            lines.append(f"\n**Semester {sem_num}:**")
            for course in courses:
                code = course.get("code", "")
                name = course.get("name", "")
                credits = course.get("credit_hours", "")
                lines.append(f"  - {code}: {name} ({credits} credit hours)")
    
    return "\n".join(lines)


@tool
def collect_student_info(user_statement: str) -> str:
    """Parse and store student information from their statement (background, interests, goals, constraints).
    
    Args:
        user_statement: What the student said about themselves, their background, interests, or goals
    
    Returns:
        Confirmation of what was understood and what additional information is needed
    """
    # Use small_llm to extract structured information
    parse_prompt = f"""Analyze this student statement and extract their information: "{user_statement}"

Identify and extract:
1. Current status: Are they a current student, recent graduate, or prospective student?
2. Current/completed program: What program are they in/did they complete? (e.g., "BS AI", "BS Computer Science")
3. Interests: What subjects or fields interest them? (e.g., "business", "AI", "data science", "entrepreneurship")
4. Career goals: What do they want to do after graduation? (e.g., "management", "start-up", "consulting", "data analyst")
5. Constraints: Any specific requirements? (e.g., "shorter program", "research-oriented", "industry-focused")
6. Level preference: What degree level do they want? (Bachelor's, Master's, PhD)

Return ONLY a JSON object:
{{
  "current_status": "current_student|recent_graduate|prospective",
  "completed_program": "program name or null",
  "interests": ["interest1", "interest2"],
  "career_goals": ["goal1", "goal2"],
  "constraints": ["constraint1"],
  "level": "bachelor|master|phd|null"
}}

Examples:
"I just graduated from BS AI and want to pursue business" -> {{"current_status": "recent_graduate", "completed_program": "BS AI", "interests": ["business"], "career_goals": [], "constraints": [], "level": null}}
"I'm in 5th semester of CS and interested in AI and ML" -> {{"current_status": "current_student", "completed_program": "BS CS", "interests": ["AI", "machine learning"], "career_goals": [], "constraints": [], "level": null}}
"Looking for a master's in data science for career in analytics" -> {{"current_status": "prospective", "completed_program": null, "interests": ["data science"], "career_goals": ["analytics"], "constraints": [], "level": "master"}}
"I want to do a Master's degree combining AI and business" -> {{"current_status": "prospective", "completed_program": null, "interests": ["AI", "business"], "career_goals": [], "constraints": [], "level": "master"}}
"Interested in MBA" -> {{"current_status": "prospective", "completed_program": null, "interests": ["business"], "career_goals": [], "constraints": [], "level": "master"}}

Now parse: "{user_statement}"
Return ONLY the JSON object."""

    try:
        response = small_llm.invoke([HumanMessage(content=parse_prompt)])
        content = response.content.strip()
        
        # Extract JSON
        json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
        if json_match:
            info = json.loads(json_match.group())
            
            # Store in global preferences (we'll create a session-aware version later)
            prefs = _get_preferences()
            
            # Update preferences
            status = info.get("current_status")
            completed_prog = info.get("completed_program")
            
            if status == "recent_graduate":
                prefs.set_student_status(False, completed_prog)
                if completed_prog:
                    prefs.preferences["completed_program"] = completed_prog
            elif status == "current_student":
                prefs.set_student_status(True, completed_prog)
                if completed_prog:
                    prefs.preferences["current_program"] = completed_prog
            
            for interest in info.get("interests", []):
                if interest and interest.lower() not in [x.lower() for x in prefs.preferences.get("interests", [])]:
                    prefs.add_interest(interest)
            
            if info.get("career_goals"):
                existing_goals = prefs.preferences.get("career_goals", [])
                new_goals = [g for g in info.get("career_goals") if g and g.lower() not in [x.lower() for x in existing_goals]]
                if new_goals:
                    prefs.update("career_goals", existing_goals + new_goals)
            
            if info.get("level"):
                prefs.preferences["level"] = info.get("level")
            
            if info.get("constraints"):
                existing_constraints = prefs.preferences.get("constraints", [])
                new_constraints = [c for c in info.get("constraints") if c and c.lower() not in [x.lower() for x in existing_constraints]]
                if new_constraints:
                    prefs.update("constraints", existing_constraints + new_constraints)
            
            # Generate response about what we understood
            parts = ["I understand that:"]
            if status == "recent_graduate":
                parts.append(f"- You recently graduated from {info.get('completed_program', 'your program')}")
            elif status == "current_student":
                parts.append(f"- You're currently studying {info.get('completed_program', 'your program')}")
            
            if info.get("interests"):
                parts.append(f"- You're interested in: {', '.join(info.get('interests'))}")
            
            if info.get("career_goals"):
                parts.append(f"- Your career goals include: {', '.join(info.get('career_goals'))}")
            
            # Check what else we need
            next_q = prefs.get_next_question()
            if next_q:
                parts.append(f"\n{next_q}")
            else:
                parts.append("\nI have enough information to recommend programs. Use the recommend_programs tool next.")
            
            return "\n".join(parts)
        else:
            return "I couldn't parse that. Could you tell me: Are you a current student, recent graduate, or prospective student? What are your interests?"
    except Exception as e:
        return f"I couldn't fully understand that. Could you clarify: What's your current status (student/graduate), what interests you, and what are your career goals?"


@tool
def recommend_programs(context: str) -> str:
    """Generate personalized program recommendations based on collected student information.
    
    Args:
        context: Brief summary of what you know about the student (optional, can be empty string)
    
    Returns:
        Top recommended programs with justifications based on the student's profile
    """
    prefs = _get_preferences()
    matcher = _get_matcher()
    
    # Filter matches to only include programs at the requested level (if specified)
    matches = matcher.find_best_matches(prefs.preferences, limit=10)
    
    # If level preference exists, filter more strictly
    if prefs.preferences.get("level"):
        level_pref = prefs.preferences["level"].lower()
        level_keywords = {
            "bachelor": ["bachelor", "bs", "b.s."],
            "master": ["master", "ms", "m.s.", "mba"],
            "phd": ["phd", "ph.d.", "doctorate"]
        }
        keywords = level_keywords.get(level_pref, [level_pref])
        
        # Only keep programs matching the level
        filtered_matches = []
        for match in matches:
            title = match["program"].get("title", "").lower()
            if any(kw in title for kw in keywords):
                filtered_matches.append(match)
        
        matches = filtered_matches[:5]  # Top 5 of the filtered list
    else:
        matches = matches[:5]
    
    if not matches:
        return "I need more information to make good recommendations. Please share: What are your interests? What degree level are you looking for? What are your career goals?"
    
    lines = ["**🎓 Personalized Program Recommendations for You:**\n"]
    
    # Add context about the student
    if prefs.preferences.get("completed_program"):
        lines.append(f"Based on your background in {prefs.preferences['completed_program']} and your interest in {', '.join(prefs.preferences.get('interests', ['your stated interests']))}, here are my top recommendations:\n")
    
    for i, match in enumerate(matches, 1):
        program = match["program"]
        score = match["score"]
        reasons = match["reasons"]
        title = program.get("title", "Unknown")
        
        # Calculate program details
        semesters = len(program.get("semesters", {}))
        total_credits = 0
        for sem_courses in program.get("semesters", {}).values():
            for course in sem_courses:
                credit_str = course.get("credit_hours", "0+0")
                try:
                    parts = credit_str.replace("NC+", "0+").split("+")
                    total_credits += sum(int(x) for x in parts if x.isdigit())
                except:
                    pass
        
        duration_years = semesters // 2 if semesters else "N/A"
        
        lines.append(f"### {i}. {title}")
        lines.append(f"**Duration:** {duration_years} years ({semesters} semesters) | **Credits:** {total_credits}")
        
        if reasons:
            lines.append("\n**Why this program is perfect for you:**")
            for reason in reasons[:4]:
                lines.append(f"  ✓ {reason}")
        
        # Add career opportunities
        if program.get("career_opportunities"):
            career_text = program.get("career_opportunities", "")[:200]
            lines.append(f"\n**Career Opportunities:** {career_text}...")
        
        # Add eligibility if available
        if program.get("eligibility"):
            lines.append(f"\n**Eligibility:** {program.get('eligibility')}")
        
        # Add URL
        if program.get("url"):
            lines.append(f"\n**More Info:** {program.get('url')}")
        
        lines.append("")  # Blank line between programs
    
    lines.append("\n**Next Steps:**")
    lines.append("1. Would you like to see the complete semester-wise course breakdown for any of these programs?")
    lines.append("2. Would you like me to compare two of these programs?")
    lines.append("3. Do you have questions about admission requirements or credit transfers?")
    
    return "\n".join(lines)


@tool
def semantic_search_programs(question: str) -> str:
    """Search degree program information using semantic similarity. Use for complex queries or when other tools don't yield results.
    
    Args:
        question: The search query
    
    Returns:
        Relevant information from the degree program database
    """
    retriever = _get_retriever()
    docs = retriever.invoke(question)
    if not docs:
        return "No semantic results found."
    # small context bundle
    top = "\n\n".join(d.page_content for d in docs[:5])
    return top[:4000]


# ============= GLOBAL SINGLETONS FOR PREFERENCE TRACKING =============

_PREFERENCES_INSTANCE: Optional[UserPreferenceCollector] = None
_MATCHER_INSTANCE: Optional[DegreeMatcher] = None


def _get_preferences() -> UserPreferenceCollector:
    global _PREFERENCES_INSTANCE
    if _PREFERENCES_INSTANCE is None:
        _PREFERENCES_INSTANCE = UserPreferenceCollector()
    return _PREFERENCES_INSTANCE


def _get_matcher() -> DegreeMatcher:
    global _MATCHER_INSTANCE
    if _MATCHER_INSTANCE is None:
        _MATCHER_INSTANCE = DegreeMatcher(_get_catalog())
    return _MATCHER_INSTANCE


# ============= AGENT BUILDER =============

class DegreeReactAgentBuilder:
    """Enhanced degree advisor agent with intelligent matching and human-in-the-loop."""

    def __init__(self):
        self.catalog = _get_catalog()
        self.retriever = _get_retriever()
        self.checkpointer = MemorySaver()
        self.agent = self._build_agent()

    def _build_agent(self):
        tools = [
            collect_student_info,
            recommend_programs,
            list_programs_by_field,
            list_programs_by_level,
            get_program_details,
            compare_programs,
            get_semester_courses,
            get_all_semester_courses,
            semantic_search_programs,
        ]

        system_prompt = (
            f"{degree_advisor_prompt}\n\n"
            "**🎯 Your Role: Personalized Degree Advisory**\n\n"
            "You are a conversational degree advisor who helps students make informed decisions about their academic path. "
            "Your approach is consultative and student-centered.\n\n"
            "**📋 Advisory Process:**\n\n"
            "1. **Understand the Student** (Use collect_student_info tool):\n"
            "   - When a student shares their background, interests, or goals, ALWAYS use collect_student_info to parse and store this\n"
            "   - Listen for: current status (student/graduate), completed program, interests, career goals, constraints\n"
            "   - Ask clarifying questions if information is missing\n"
            "   - Example triggers: 'I graduated from...', 'I want to pursue...', 'I'm interested in...'\n\n"
            "2. **Gather Missing Context** (Ask directly, don't use a tool):\n"
            "   - If you need more information, ASK in your response (don't call a tool for questions)\n"
            "   - Key questions: What's your background? What interests you? What are your career goals? What degree level?\n"
            "   - Be conversational: 'That's great! What specific aspects of [field] interest you most?'\n\n"
            "3. **Provide Personalized Recommendations** (Use recommend_programs tool):\n"
            "   - Once you have sufficient information (interests + level OR completed program + new interests), use recommend_programs\n"
            "   - This will give top 3-5 programs with justifications based on their profile\n"
            "   - Each recommendation explains WHY it fits their background and goals\n\n"
            "4. **Provide Detailed Information** (Use specific tools as needed):\n"
            "   - For complete semester breakdown: get_all_semester_courses ('program name')\n"
            "   - For specific semester: get_semester_courses ('program name, semester number')\n"
            "   - For program details: get_program_details ('program title')\n"
            "   - For comparisons: compare_programs ('Program A vs Program B')\n"
            "   - For broad searches: list_programs_by_field or list_programs_by_level\n\n"
            "**🎓 Available FAST-NU Islamabad Programs:**\n"
            "- Bachelor's: CS, AI, Software Engineering, Data Science, Cybersecurity, Business Analytics, BBA, etc.\n"
            "- Master's: MS AI, MS CS, MS Data Science, MBA, MS Business Analytics, etc.\n"
            "- PhD programs in various fields\n\n"
            "**💡 Best Practices:**\n"
            "- Be warm and encouraging: 'Congratulations on completing BS AI!', 'That's an exciting direction!'\n"
            "- Acknowledge their background: 'Your AI foundation will be valuable for...'\n"
            "- Explain connections: 'This program combines your technical skills with business strategy'\n"
            "- Offer next steps: 'Would you like to see the course breakdown?', 'Should I compare these two options?'\n"
            "- Provide URLs to official program pages when available\n\n"
            "Remember: You're not just listing programs—you're helping students make life-changing decisions. "
            "Take time to understand their unique situation and provide thoughtful, justified recommendations."
        )

        self.system_prompt_text = system_prompt

        return create_react_agent(
            model=llm,
            tools=tools,
            checkpointer=self.checkpointer,
            name="Degree Advisor",
        )

    def get_agent(self):
        return self.agent

    def stream(self, question: str, session_id: str = "default"):
        """Stream responses for a given question with session-specific conversation history.
        
        Args:
            question: The user's question
            session_id: Unique session identifier to maintain separate conversation contexts
        """
        config = {"configurable": {"thread_id": f"degree_react::{session_id}"}}
        for step in self.agent.stream(
            {"messages": [SystemMessage(content=getattr(self, "system_prompt_text", "")), HumanMessage(content=question)]},
            config,
            stream_mode="values",
        ):
            if step.get("messages"):
                last_msg = step["messages"][-1]
                if hasattr(last_msg, "content") and isinstance(last_msg.content, str):
                    yield last_msg.content


# ============= SIMPLE RAG (BACKWARDS COMPATIBILITY) =============

DEGREE_ADVISOR_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template=(
        "You are a helpful and knowledgeable Degree Advisor for FAST - National University (FAST-NU) Islamabad campus.\n"
        "ONLY provide program details and recommendations for FAST Islamabad campus. If a user asks about other institutions, politely state you are restricted to FAST Islamabad and offer to suggest equivalent FAST programs where possible.\n\n"
        "Context:\n{context}\n\nQuestion: {question}\nAnswer:"
    ),
)


class DegreeAdvisorAgent:
    """Degree advisor using a simple RAG flow (retriever + prompt + LLM)."""

    def __init__(self):
        self.retriever = DegreeVectorStore().get_retriever(k=15)

    def _build_context(self, docs, top_k: int = 5) -> str:
        return "\n".join(doc.page_content for doc in docs[:top_k])

    def invoke(self, question: str) -> str:
        docs = self.retriever.invoke(question)
        context = self._build_context(docs)
        prompt_text = DEGREE_ADVISOR_PROMPT.format(context=context, question=question)
        try:
            resp = llm.invoke([HumanMessage(content=prompt_text)])
            return resp.content if hasattr(resp, "content") else str(resp)
        except Exception as e:
            return f"Error processing request: {str(e)}"

    def stream(self, question: str):
        docs = self.retriever.invoke(question)
        context = self._build_context(docs)
        prompt_text = DEGREE_ADVISOR_PROMPT.format(context=context, question=question)
        try:
            stream = llm.stream([HumanMessage(content=prompt_text)])
            for chunk in stream:
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
        except Exception as e:
            yield f"Error processing request: {str(e)}"


def get_degree_advisor_agent() -> DegreeAdvisorAgent:
    return DegreeAdvisorAgent()


if __name__ == "__main__":
    builder = DegreeReactAgentBuilder()
    test_questions = [
        "List down all the semester wise courses for BS AI?",
        "What courses do I need to take in semester 5 of BS Computer Science?",
        "Compare BS AI vs BS Computer Science",
    ]
    
    for q in test_questions:
        print(f"\n=== Question: {q} ===")
        for resp in builder.stream(q):
            print(resp, end="", flush=True)
        print("\n" + "="*50 + "\n")
