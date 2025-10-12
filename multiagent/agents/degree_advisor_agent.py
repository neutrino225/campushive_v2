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
from langchain.agents import Tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from config import embeddings, llm
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
        
        # Interest matching (highest weight)
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
        
        # Level matching
        if preferences.get("level"):
            level_match = preferences["level"].lower() in title.lower()
            if level_match:
                score += 20
                reasons.append(f"Matches your {preferences['level']} level preference")
        
        # Career goals matching
        career_opps = str(program.get("career_opportunities", "")).lower()
        for goal in preferences.get("career_goals", []):
            if goal.lower() in career_opps:
                score += 15
                reasons.append(f"Aligns with your career goal: {goal}")
        
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

class DegreeReactAgentBuilder:
    """Enhanced degree advisor agent with intelligent matching and human-in-the-loop."""

    def __init__(self):
        self.catalog = DegreeCatalog()
        self.retriever = DegreeVectorStore().get_retriever(k=20)
        self.preferences = UserPreferenceCollector()
        self.matcher = DegreeMatcher(self.catalog)
        self.checkpointer = MemorySaver()
        self.agent = self._build_agent()

    def _wrap(self, fn: Callable[[str], str], name: str, description: str) -> Tool:
        return Tool(name=name, func=fn, description=description)

    # ----- tool impls (single-string inputs) -----
    def _tool_by_field(self, field: str) -> str:
        # JSON first
        json_hits = self.catalog.by_field(field, limit=20)
        # vector assist
        docs = self.retriever.invoke(f"degree programs in {field}")
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

    def _tool_by_level(self, level: str) -> str:
        json_hits = self.catalog.by_level(level, limit=30)
        docs = self.retriever.invoke(f"{level} degree programs")
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

    def _tool_details(self, program_title: str) -> str:
        # JSON exact/fuzzy
        p = self.catalog.details(program_title)
        if p:
            return _format_details(p)
        # semantic fallback
        docs = self.retriever.invoke(f"{program_title} program details")
        for d in docs:
            if program_title.lower() in str(d.metadata.get("title", "")).lower():
                return d.page_content
        return docs[0].page_content if docs else f"No detailed information found for {program_title}."

    def _tool_compare(self, text: str) -> str:
        # Expect input like "Program A vs Program B" or "Program A | Program B"
        raw = (text or "").strip()
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
        da = self.catalog.details(a)
        db = self.catalog.details(b)
        if not da:
            docs_a = self.retriever.invoke(f"{a} program details")
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
            docs_b = self.retriever.invoke(f"{b} program details")
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

    def _tool_recommend(self, text: str) -> str:
        """Intelligent recommendations based on collected preferences."""
        # Use matcher to find best programs based on stored preferences
        matches = self.matcher.find_best_matches(self.preferences.preferences, limit=5)
        
        if not matches:
            return "I need more information about your interests to provide good recommendations. What field or subjects interest you?"
        
        lines = ["**Based on your preferences, here are my top recommendations:**\n"]
        
        for i, match in enumerate(matches, 1):
            program = match["program"]
            score = match["score"]
            reasons = match["reasons"]
            
            lines.append(f"**{i}. {program.get('title', 'Unknown')}** (Match Score: {score})")
            if reasons:
                lines.append("   Why this program:")
                for reason in reasons[:3]:
                    lines.append(f"   - {reason}")
            
            # Add quick summary
            semesters = len(program.get("semesters", {}))
            if semesters:
                lines.append(f"   - Duration: {semesters} semesters")
            lines.append("")
        
        lines.append("Would you like more details about any of these programs?")
        return "\n".join(lines)
    
    def _tool_collect_preferences(self, text: str) -> str:
        """Collect user preferences from their input."""
        text_lower = text.lower()
        
        # Detect current student status
        if any(phrase in text_lower for phrase in ["current student", "already enrolled", "studying", "my program"]):
            # Try to extract program name
            for title in self.catalog._index_by_title.keys():
                if title in text_lower:
                    self.preferences.set_student_status(True, title)
                    return f"I understand you're a current {title} student. How can I help you with your program?"
            self.preferences.set_student_status(True)
            return "I understand you're a current student. Which program are you enrolled in?"
        
        # Detect prospective student
        if any(phrase in text_lower for phrase in ["prospective", "interested in applying", "want to join", "looking for"]):
            self.preferences.set_student_status(False)
            return "Great! I'll help you find the right program. What are your main interests?"
        
        # Extract level preference
        for level in ["bachelor", "master", "phd", "bs", "ms", "undergraduate", "graduate"]:
            if level in text_lower:
                self.preferences.update("level", level)
                return f"Noted! You're interested in {level}-level programs."
        
        # Extract interests
        interests = []
        interest_keywords = ["ai", "artificial intelligence", "machine learning", "data science", 
                           "computer science", "software engineering", "cybersecurity", "business", 
                           "finance", "accounting", "analytics"]
        for keyword in interest_keywords:
            if keyword in text_lower:
                interests.append(keyword)
        
        if interests:
            for interest in interests:
                self.preferences.add_interest(interest)
            return f"I've noted your interests: {', '.join(interests)}. This will help me recommend suitable programs."
        
        return "I've recorded that information. Feel free to share more about your interests or ask for recommendations!"
    
    def _tool_semester_courses(self, text: str) -> str:
        """Get courses for a specific semester of a program."""
        # Parse input: "program name, semester number"
        parts = text.split(",")
        if len(parts) < 2:
            return "Please provide both program name and semester number (e.g., 'BS Computer Science, 3')"
        
        program_title = parts[0].strip()
        try:
            semester = int(parts[1].strip())
        except ValueError:
            return "Please provide a valid semester number."
        
        courses = self.catalog.get_semester_courses(program_title, semester)
        if not courses:
            return f"No courses found for {program_title}, Semester {semester}."
        
        lines = [f"**{program_title} - Semester {semester} Courses:**\n"]
        for course in courses:
            code = course.get("code", "")
            name = course.get("name", "")
            credits = course.get("credit_hours", "")
            lines.append(f"- {code}: {name} ({credits} credit hours)")
        
        return "\n".join(lines)

    def _tool_semantic(self, question: str) -> str:
        docs = self.retriever.invoke(question)
        if not docs:
            return "No semantic results found."
        # small context bundle
        top = "\n\n".join(d.page_content for d in docs[:5])
        return top[:4000]

    def _tool_hybrid(self, question: str) -> str:
        # Combine JSON search signal and semantic context
        json_hits = self.catalog.search(question, limit=15)
        semantic_blob = self._tool_semantic(question)
        if not json_hits and "No semantic results" in semantic_blob:
            return "No results found. Please rephrase your question or specify the program/level."
        lines = []
        if json_hits:
            lines.append("Top matches (catalog):")
            lines += [_format_program_line(p) for p in json_hits[:10]]
        if semantic_blob and not semantic_blob.startswith("No semantic results"):
            lines += ["", "Relevant excerpts (semantic):", semantic_blob]
        return "\n".join(lines)

    def _build_agent(self):
        tools: List[Tool] = [
            self._wrap(
                self._tool_by_field,
                name="list_programs_by_field",
                description="List all degree programs in a specific field (e.g., 'Computer Science', 'Business', 'AI'). Use this when user asks about programs in a field."
            ),
            self._wrap(
                self._tool_by_level,
                name="list_programs_by_level",
                description="List all degree programs at a specific level (e.g., 'Bachelor', 'Master', 'PhD', 'BS', 'MS'). Use when user asks about undergraduate or graduate programs."
            ),
            self._wrap(
                self._tool_details,
                name="get_program_details",
                description="Get comprehensive details about a specific degree program including vision, mission, career opportunities, and structure. Input: exact program title."
            ),
            self._wrap(
                self._tool_compare,
                name="compare_programs",
                description="Compare two degree programs side-by-side. Input format: 'Program A vs Program B' or 'Program A | Program B'."
            ),
            self._wrap(
                self._tool_recommend,
                name="recommend_programs",
                description="Provide intelligent program recommendations based on collected user preferences. Uses stored preferences for personalized suggestions."
            ),
            self._wrap(
                self._tool_collect_preferences,
                name="collect_user_preferences",
                description="Collect and store user preferences (interests, level, student status, career goals). Use when user shares information about themselves."
            ),
            self._wrap(
                self._tool_semester_courses,
                name="get_semester_courses",
                description="Get list of courses for a specific semester of a program. Input format: 'program name, semester number' (e.g., 'BS Computer Science, 3')."
            ),
            self._wrap(
                self._tool_semantic,
                name="semantic_search",
                description="Search degree program corpus using semantic similarity. Use for complex queries or when catalog search doesn't yield results."
            ),
        ]

        system_prompt = (
            f"{degree_advisor_prompt}\n\n"
            "**Your Approach:**\n"
            "1. When a user first asks about choosing a program, ask them clarifying questions DIRECTLY (don't use a tool for this):\n"
            "   - Are they a current student or prospective student?\n"
            "   - If prospective: What are their interests? What level (Bachelor's/Master's/PhD)?\n"
            "   - If current: What program and semester are they in?\n"
            "2. Use 'collect_user_preferences' to STORE their responses (not to ask questions)\n"
            "3. Once you have enough information, use 'recommend_programs' to provide personalized suggestions\n"
            "4. For current students: Use tools to provide detailed information about their program, courses, and requirements\n"
            "5. Always use exact program titles when calling tools\n"
            "6. Provide specific, actionable advice based on official program data\n\n"
            "**Available Data:**\n"
            "- Complete semester-wise course breakdown for all programs\n"
            "- Program eligibility, vision, mission, and career opportunities\n"
            "- Credit hours and duration information\n"
            "- Program educational objectives (PEOs) and learning outcomes (PLOs)\n\n"
            "**Important:** When you need more information from the user, ASK THEM DIRECTLY in your response. "
            "Don't use a tool to ask questions - just include the question in your natural response to the user. "
            "Be helpful, accurate, and conversational. Guide users through their decision-making process."
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


# ---------------- Simple RAG (backwards compatibility) ---------------- #

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


# Utility function to get agent instance (back-compat)
def get_degree_advisor_agent() -> DegreeAdvisorAgent:
    return DegreeAdvisorAgent()


if __name__ == "__main__":
    # Quick manual test with pretty printing

    builder = DegreeReactAgentBuilder()
    agent = builder.get_agent()
    test_questions = [
        "I am a current BS Computer Science student in semester 3. What courses do I need to take next semester?",
        "Can you recommend some undergraduate programs in AI and Data Science?",
        "What are the career opportunities for MS Software Engineering graduates?",
        "Compare BS Computer Science vs BS Software Engineering.",
        "List all Master's programs available at FAST Islamabad.",
        "Tell me about the eligibility criteria for the PhD in Computer Science program.",
        "I am interested in business and finance. Which programs should I consider?",
    ]
    
    for q in test_questions:
        print(f"\n=== Question: {q} ===")
        for resp in builder.stream(q):
            print(resp, end="", flush=True)
        print("\n" + "="*50 + "\n")

