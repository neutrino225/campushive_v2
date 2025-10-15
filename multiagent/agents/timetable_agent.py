import pandas as pd
import re
import json
from typing import List, Tuple, Set, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from multiagent.agents.degree_advisor_agent import DegreeCatalog
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain.tools import tool
from rapidfuzz import fuzz, process
from langchain.agents import Tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parents[2]
sys.path.append(str(project_root))

from config import llm, small_llm

# Global catalog instance for accessing degree program data
_CATALOG_INSTANCE: Optional['DegreeCatalog'] = None

def _get_catalog():
    """Lazy load the degree catalog to avoid circular imports and startup overhead."""
    global _CATALOG_INSTANCE
    if _CATALOG_INSTANCE is None:
        from multiagent.agents.degree_advisor_agent import DegreeCatalog
        _CATALOG_INSTANCE = DegreeCatalog()
    return _CATALOG_INSTANCE

class CourseTimetable(BaseModel):
    course: str = Field(description="Full course name as present in the timetable")
    room_number: str = Field(description="Room number")
    time_slot: str = Field(description="Time slot")
    day: str = Field(description="Day of the week when the course is scheduled")


class CourseTimetableList(BaseModel):
    courses: List[CourseTimetable]

class TimetableAgentBuilder:
    def __init__(self, timetable_path: str, mapping_path: str):
        self.data_df = pd.read_csv(timetable_path)
        self.mappings = self._load_mappings(mapping_path)
        self.llm = llm
        self.parser = PydanticOutputParser(pydantic_object=CourseTimetableList)
        self.prompt = self._build_prompt()
        self.fallback_prompt = self._build_fallback_prompt()
        self.checkpointer = MemorySaver()
        
        # Preprocess course data for better matching
        self._preprocess_course_data()
        
        self.agent = self._build_agent()

    def _load_mappings(self, path: str) -> dict:
        with open(path, "r") as f:
            return json.load(f)

    def _normalize(self, text: str) -> str:
        """Enhanced normalization for better matching."""
        if not isinstance(text, str):
            return ""

        # Convert to lowercase
        text = text.lower()

        # Normalize unicode dashes to ASCII hyphen
        text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)

        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove common punctuation that doesn't affect course names
        text = re.sub(r"[^\w\s\-()]", " ", text)

        # Apply mappings - lowercase the keys and values
        for k, v in self.mappings.items():
            text = text.replace(k.lower(), v.lower())

        # Handle section codes (e.g., "cs-a" -> "cs a")
        text = re.sub(r"([a-z]{2,})-([a-z])", r"\1 \2", text)

        # Handle parentheses and brackets (but preserve content)
        # For courses like "Gen AI (CS-A, G-1)", we want to keep the section info
        text = re.sub(r"[\(\)\[\]]", " ", text)

        # Handle common abbreviations
        # Note: We need to be careful with order - do contractions before expansions
        # to avoid double-replacement issues
        
        # Course name expansions (for better matching)
        text = text.replace("generative ai", "gen ai")
        text = text.replace("generative artificial intelligence", "gen ai")
        
        # Remove group identifiers like "G-1", "G-2" which are internal grouping codes
        text = re.sub(r'\bg-\d+\b', '', text)
        
        # British/American variants
        text = text.replace("behaviour", "behavior")
        text = text.replace("organisation", "organization")
        
        # Contract long forms to their common short forms used in CSV
        # These match the patterns in structured_timetable.csv
        text = text.replace("organizational", "org")
        text = text.replace("organization", "org")
        text = text.replace("reinforcement learning", "reinf learning")  # Contract before individual word replacements
        text = text.replace(" leadership", "")  # Remove "leadership" as it's not in course names
        text = text.replace("computer vision", "comp vision")  # Contract computer vision as a phrase
        
        # Remove the word "section" entirely to improve matching
        text = re.sub(r'\bsection\b', '', text)

        # Remove extra whitespace again
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    def _extract_course_phrases(self, query: str) -> List[str]:
        """Enhanced course phrase extraction with better pattern recognition."""
        # IMPORTANT: Split BEFORE normalization to preserve separators
        # Normalize will remove commas, so we split first
        parts = re.split(r'(\band\b|,|;|\n)', query)

        # Filter out the separators and empty strings
        phrases = [p.strip() for p in parts if p.strip() and p not in ["and", ",", ";", "\n"]]

        # Normalize each phrase separately AFTER splitting
        phrases = [self._normalize(p) for p in phrases]

        # Process each phrase to identify course codes and patterns
        result = []
        for i, phrase in enumerate(phrases):
            # Check if the phrase looks like a course code (e.g., "cs a", "ds b")
            if re.match(r'^[a-z]{2,}\s+[a-z]$', phrase) and i > 0:
                # Combine with the previous phrase
                result[-1] += f" {phrase}"
            else:
                # Check for section indicators within the phrase
                phrase = re.sub(r'(\b[a-z]{2,}\b)\s+section\s+([a-z])', r'\1 \2', phrase)
                phrase = re.sub(r'(\b[a-z]{2,}\b)\s+sec\s+([a-z])', r'\1 \2', phrase)
                phrase = re.sub(r'(\b[a-z]{2,}\b)\s+([a-z])\s*section', r'\1 \2', phrase)

                result.append(phrase)

        return result

    def _get_unique_courses(self) -> List[str]:
        return self.data_df["Class"].unique().tolist()

    def _recognize_course_patterns(self, phrase: str) -> List[str]:
        """Recognize and extract course patterns from a phrase."""
        # Clean up the phrase
        phrase = phrase.strip()
        
        # Look for section code pattern (e.g., "ai a", "cs b")
        section_match = re.search(r'\b([a-z]{2,})\s+([a-z])\b', phrase)
        
        if section_match:
            dept_code = section_match.group(1)
            section_letter = section_match.group(2)
            
            # Extract the course name (everything before the section code)
            course_name = phrase[:section_match.start()].strip()
            
            if course_name:
                # Return course name with section
                return [f"{course_name} {dept_code} {section_letter}"]
            else:
                # Just the section code
                return [f"{dept_code} {section_letter}"]
        
        # If no section pattern found, return the phrase as-is
        return [phrase]

    def _extract_keywords(self, course_name: str) -> List[str]:
        """Extract keywords from a course name."""
        # Normalize the course name
        normalized = self._normalize(course_name)

        # Split into words
        words = normalized.split()

        # Filter out common words
        common_words = {"cs", "ds", "ai", "cy", "se", "section", "sec", "the", "and", "or", "in", "on", "at", "to", "for", "lab", "laboratory"}
        keywords = [word for word in words if word not in common_words and len(word) > 1]

        return keywords

    def _preprocess_course_data(self):
        """Preprocess course data for better matching."""
        # Create a dictionary of normalized course names to original names
        self.normalized_to_original = {}

        for course in self.data_df["Class"].unique():
            normalized = self._normalize(course)
            self.normalized_to_original[normalized] = course

        # Create a mapping of course keywords to courses
        self.course_keywords = {}
        for course in self.data_df["Class"].unique():
            # Extract keywords from course name
            keywords = self._extract_keywords(course)
            for keyword in keywords:
                if keyword not in self.course_keywords:
                    self.course_keywords[keyword] = []
                self.course_keywords[keyword].append(course)

        # Create a mapping of course acronyms to courses
        self.course_acronyms = {}
        for course in self.data_df["Class"].unique():
            # Extract potential acronyms
            words = self._normalize(course).split()
            if len(words) > 1:
                acronym = "".join([word[0] for word in words if word])
                if acronym not in self.course_acronyms:
                    self.course_acronyms[acronym] = []
                self.course_acronyms[acronym].append(course)

    def _filter_by_keywords(self, query: str, candidates: List[str]) -> List[str]:
        """Filter candidates by checking if key course terms match.
        
        This prevents false matches like 'Generative AI' matching 'PF'.
        """
        query_lower = query.lower()
        
        # Extract key course keywords from query (excluding section codes)
        query_keywords = set()
        for word in query_lower.split():
            # Skip section codes and common words
            if word not in ['cs', 'ai', 'ds', 'se', 'ee', 'cy', 'a', 'b', 'c', 'd', 'e', 'section', 'the', 'and', 'or']:
                # Add significant words
                if len(word) > 2:
                    query_keywords.add(word)
        
        # Also check for common abbreviations
        abbreviation_map = {
            'gen': 'generative',
            'ai': 'artificial intelligence',
            'ml': 'machine learning',
            'dl': 'deep learning',
            'cv': 'computer vision',
            'nlp': 'natural language processing',
            'pf': 'programming fundamentals',
            'obl': 'organizational behavior leadership',
            'org': 'organizational',
        }
        
        # Expand abbreviations in query
        expanded_keywords = set(query_keywords)
        for abbr, full in abbreviation_map.items():
            if abbr in query_keywords:
                expanded_keywords.update(full.split())
        
        # Filter candidates
        filtered = []
        for candidate in candidates:
            candidate_lower = candidate.lower()
            
            # Check if at least one key keyword appears in candidate
            has_match = False
            for keyword in expanded_keywords:
                if keyword in candidate_lower:
                    has_match = True
                    break
            
            # Also check for strong negative matches (prevent wrong course)
            is_wrong_course = False
            
            # If query has "generative" or "gen ai", don't match "pf" (programming fundamentals)
            if any(term in query_lower for term in ['generative', 'gen ai', 'genai']):
                if re.search(r'\bpf\b', candidate_lower) and 'gen' not in candidate_lower:
                    is_wrong_course = True
            
            # If query has "pf" or "programming", don't match "gen ai"
            if any(term in query_lower for term in ['pf ', ' pf', 'programming fundamental']):
                if 'gen' in candidate_lower and 'pf' not in candidate_lower:
                    is_wrong_course = True
            
            if has_match and not is_wrong_course:
                filtered.append(candidate)
        
        return filtered if filtered else candidates  # Fallback to original if no matches

    def _fuzzy_match_courses(self, query: str, threshold: int = 60) -> Tuple[Set[str], List[str]]:
        """Enhanced fuzzy matching using multiple strategies with keyword filtering."""
        matched = set()
        suggestions = []
        phrases = self._extract_course_phrases(query)
        unique_courses = self._get_unique_courses()
        
        # PRE-FILTER: Remove obviously wrong courses based on keywords
        unique_courses = self._filter_by_keywords(query, unique_courses)

        for phrase in phrases:
            norm_phrase = self._normalize(phrase)
            
            # Recognize course patterns in the phrase
            course_candidates = self._recognize_course_patterns(norm_phrase)

            for candidate in course_candidates:
                # Strategy 1: Get multiple matches and score them based on token overlap
                normalized_courses = [self._normalize(course) for course in unique_courses]
                
                # Get top matches instead of just one
                results = process.extract(
                    candidate,
                    normalized_courses,
                    scorer=fuzz.WRatio,
                    score_cutoff=threshold,
                    limit=10  # Get top 10 matches
                )

                if results:
                    # Calculate token overlap score for each result
                    candidate_tokens = set(candidate.split())
                    scored_results = []
                    
                    for normalized_match, score, _ in results:
                        match_tokens = set(normalized_match.split())
                        
                        # Calculate token overlap (Jaccard similarity)
                        if candidate_tokens and match_tokens:
                            overlap = len(candidate_tokens & match_tokens)
                            overlap_ratio = overlap / max(len(candidate_tokens), len(match_tokens))
                            
                            # Combined score: fuzzy score + token overlap bonus
                            combined_score = score + (overlap_ratio * 20)  # 20 point bonus for perfect overlap
                            scored_results.append((normalized_match, combined_score, overlap_ratio))
                    
                    # Sort by combined score
                    scored_results.sort(key=lambda x: (x[1], x[2]), reverse=True)
                    
                    # Get the best match
                    if scored_results:
                        best_normalized_match = scored_results[0][0]
                        original_course = next(
                            (course for course in unique_courses
                             if self._normalize(course) == best_normalized_match),
                            None
                        )
                        if original_course:
                            matched.add(original_course)
                            continue

                # Strategy 2: Token-based matching
                tokens = candidate.split()
                if len(tokens) > 1 and not matched:
                    # Try matching with subsets of tokens
                    for i in range(len(tokens)):
                        for j in range(i+1, len(tokens)+1):
                            subset = " ".join(tokens[i:j])
                            results = process.extract(
                                subset,
                                normalized_courses,
                                scorer=fuzz.WRatio,
                                score_cutoff=threshold,
                                limit=5
                            )

                            if results:
                                # Use the same token overlap scoring
                                subset_tokens = set(subset.split())
                                scored_results = []
                                
                                for normalized_match, score, _ in results:
                                    match_tokens = set(normalized_match.split())
                                    if subset_tokens and match_tokens:
                                        overlap = len(subset_tokens & match_tokens)
                                        overlap_ratio = overlap / max(len(subset_tokens), len(match_tokens))
                                        combined_score = score + (overlap_ratio * 20)
                                        scored_results.append((normalized_match, combined_score))
                                
                                scored_results.sort(key=lambda x: x[1], reverse=True)
                                
                                if scored_results:
                                    best_normalized_match = scored_results[0][0]
                                    original_course = next(
                                        (course for course in unique_courses
                                         if self._normalize(course) == best_normalized_match),
                                        None
                                    )
                                    if original_course:
                                        matched.add(original_course)
                                        break

                # Strategy 3: Partial matching with lower threshold
                if not matched:
                    results = process.extract(
                        candidate,
                        normalized_courses,
                        scorer=fuzz.partial_ratio,
                        score_cutoff=max(40, threshold - 20),
                        limit=5
                    )

                    if results:
                        # Use token overlap scoring for partial matches too
                        candidate_tokens = set(candidate.split())
                        scored_results = []
                        
                        for normalized_match, score, _ in results:
                            match_tokens = set(normalized_match.split())
                            if candidate_tokens and match_tokens:
                                overlap = len(candidate_tokens & match_tokens)
                                overlap_ratio = overlap / max(len(candidate_tokens), len(match_tokens))
                                combined_score = score + (overlap_ratio * 20)
                                scored_results.append((normalized_match, combined_score))
                        
                        scored_results.sort(key=lambda x: x[1], reverse=True)
                        
                        if scored_results:
                            best_normalized_match = scored_results[0][0]
                            original_course = next(
                                (course for course in unique_courses
                                 if self._normalize(course) == best_normalized_match),
                                None
                            )
                            if original_course:
                                suggestions.append(f"{original_course} ({scored_results[0][1]:.1f}%)")

                # Strategy 4: Acronym matching
                if not matched:
                    tokens = candidate.split()
                    if len(tokens) > 1:
                        # Create an acronym from the tokens
                        acronym = "".join([token[0] for token in tokens if token])
                        if acronym in self.course_acronyms:
                            for course in self.course_acronyms[acronym]:
                                suggestions.append(f"{course} (acronym match)")

        # Deduplicate suggestions while preserving order
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            if s not in seen:
                unique_suggestions.append(s)
                seen.add(s)

        return matched, unique_suggestions

    def _expand_course_with_related(self, matched_courses: Set[str]) -> Set[str]:
        """Expand matched courses to include related courses (labs, tutorials, etc.)."""
        expanded = set(matched_courses)
        
        for course in matched_courses:
            # Extract base course name and section
            base_name = course.lower()
            
            # Look for related courses (lab, tutorial, recitation)
            for potential_course in self.data_df["Class"].unique():
                potential_lower = potential_course.lower()
                
                # Check if this is a related course (lab, tutorial, etc.)
                if any(keyword in potential_lower for keyword in ['lab', 'tutorial', 'recitation', 'practical']):
                    # Extract the base name without lab/tutorial
                    potential_base = re.sub(r'\s*(lab|tutorial|recitation|practical)\s*', ' ', potential_lower).strip()
                    course_base = re.sub(r'\s*(lab|tutorial|recitation|practical)\s*', ' ', base_name).strip()
                    
                    # If the base names match (accounting for abbreviations), include it
                    if potential_base in course_base or course_base in potential_base:
                        expanded.add(potential_course)
        
        return expanded
    
    def _get_alternative_sections(self, course_name: str, original_section: str) -> List[Tuple[str, str]]:
        """Find alternative sections offering the same course."""
        alternatives = []
        
        # Extract base course name (without section)
        base_name = re.sub(r'\s*\([^)]+\)\s*$', '', course_name).strip()
        
        # Search for similar courses in different sections
        for full_course in self.data_df["Class"].unique():
            # Extract this course's base name
            this_base = re.sub(r'\s*\([^)]+\)\s*$', '', full_course).strip()
            
            # If base names are similar and it's a different section
            if self._normalize(base_name) == self._normalize(this_base):
                # Extract section from full course name
                section_match = re.search(r'\(([^)]+)\)$', full_course)
                if section_match:
                    section = section_match.group(1)
                    if section.lower() != original_section.lower():
                        alternatives.append((full_course, section))
        
        return alternatives

    def _extract_course_schedule(self, query: str) -> Tuple[CourseTimetableList, List[str]]:
        """Return (CourseTimetableList, suggestions) with improved course extraction."""
        # Extract phrases using the enhanced method
        phrases = self._extract_course_phrases(query)

        # Match each phrase individually (don't join them - that creates gibberish)
        matched_courses = set()
        suggestions = []
        
        for phrase in phrases:
            # Recognize course patterns
            patterns = self._recognize_course_patterns(phrase)
            
            # Try fuzzy matching on each pattern
            for pattern in patterns:
                matches, suggs = self._fuzzy_match_courses(pattern)
                matched_courses.update(matches)
                suggestions.extend(suggs)
        
        # ENHANCEMENT: Expand to include related courses (labs, tutorials)
        if matched_courses:
            matched_courses = self._expand_course_with_related(matched_courses)

        filtered_df = self.data_df[self.data_df["Class"].isin(matched_courses)]
        
        # Filter out junk entries (e.g., "Lab" with "Lab" room and "Room" time)
        filtered_df = filtered_df[
            ~((filtered_df["Class"] == "Lab") & 
              (filtered_df["Room"] == "Lab") & 
              (filtered_df["Time"] == "Room"))
        ]
        
        # Filter out FYP (Final Year Project) entries - FYP is self-scheduled with supervisors
        filtered_df = filtered_df[
            ~filtered_df["Class"].str.contains("FYP|Final Year Project", case=False, na=False)
        ]
        
        timetable = CourseTimetableList(
            courses=[
                CourseTimetable(
                    course=row["Class"],
                    room_number=row["Room"],
                    time_slot=row["Time"],
                    day=row["Day"],
                )
                for _, row in filtered_df.iterrows()
            ]
        )
        return timetable, suggestions

    def _to_json_list(self, timetable_list: CourseTimetableList) -> str:
        return json.dumps(
            [
                {
                    "course": c.course,
                    "day": c.day,
                    "time_slot": c.time_slot,
                    "room_number": c.room_number,
                }
                for c in timetable_list.courses
            ],
            indent=2,
        )

    def _build_prompt(self) -> PromptTemplate:
        return PromptTemplate(
            template="""
You are a helpful assistant filtering a course timetable.

Here is the course schedule data:
{filtered_courses}

The user query is:
"{query}"

Instructions:
- Identify the course names mentioned in the query (e.g., "PF (CS-A)").
- For each matching course, return ALL entries for ALL days and time slots where it appears.
- Use the exact course names from the data provided.
- If no exact matches are found, try to find the closest matches based on course names.
- Consider variations in course names (e.g., "Info Sec" for "Information Security").
- Handle section codes properly (e.g., "CS-A" means Computer Science section A).
- If multiple courses match, include all of them.
- Output valid JSON in this format:

{format_instructions}

Do not explain anything. Just output valid JSON.
""",
            input_variables=["query", "filtered_courses"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def _build_fallback_prompt(self) -> PromptTemplate:
        return PromptTemplate(
            template="""
You are a helpful assistant filtering a course timetable.

The user query is:
"{query}"

I couldn't find exact matches for this query. The closest suggestions are:
{suggestions}

Instructions:
- Based on the suggestions, try to find the most likely matches in the timetable data.
- If there are no good matches, return an empty list.
- Output valid JSON in this format:

{format_instructions}

Do not explain anything. Just output valid JSON.
""",
            input_variables=["query", "suggestions"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def _generate_structured_timetable(
        self, query: str, extracted: CourseTimetableList, suggestions: List[str] = None
    ) -> CourseTimetableList:
        try:
            if extracted.courses:
                chain = self.prompt | self.llm | self.parser
                return chain.invoke(
                    {"query": query, "filtered_courses": self._to_json_list(extracted)}
                )
            elif suggestions:
                chain = self.fallback_prompt | self.llm | self.parser
                return chain.invoke(
                    {"query": query, "suggestions": ", ".join(suggestions)}
                )
            else:
                return CourseTimetableList(courses=[])
        except Exception as e:
            print(f"Error generating structured timetable: {e}")
            return extracted if extracted.courses else CourseTimetableList(courses=[])

    def _build_agent(self):
        @tool
        def lookup_semester_courses(program_and_semester: str) -> str:
            """
            **IMPORTANT: Use this tool ONLY when the user asks for timetable but does NOT specify exact course names/codes.**
            
            This tool fetches the list of courses offered in a specific semester of a degree program.
            Use ONLY when you need to find out what courses are in a semester before looking up timetables.
            
            **When to use:**
            - User says "my timetable for 7th semester BS AI" without listing courses
            - User says "complete timetable for semester 5 of BS CS" without course names
            
            **When NOT to use:**
            - User provides specific course names (e.g., "PF CS-A", "OBL AI-D") - use get_timetable directly
            - User provides course codes with sections - use get_timetable directly
            
            **AFTER using this tool:**
            1. You will get a list of core/required courses
            2. Ask the user clarifying questions:
               - "What section are you in?" (e.g., CS-A, AI-D)
               - "Do you have any electives this semester? If yes, which ones?"
            3. Once you have section info and elective choices, use get_timetables with the complete course list
            
            Args:
                program_and_semester: Program name and semester (e.g., "BS AI, 7" or "BS Computer Science, 5")
            
            Returns:
                Formatted list of courses with codes and credit hours for that semester
            """
            catalog = _get_catalog()
            
            # Use small_llm to parse the input
            parse_prompt = f"""Extract program name and semester from: "{program_and_semester}"

Return ONLY JSON:
{{
  "program": "program name or abbreviation",
  "semester": semester_number
}}

Keep abbreviations (BS, MS, AI, CS, etc.) as-is.

Examples:
"BS AI, 7" -> {{"program": "BS AI", "semester": 7}}
"7th semester of BS AI" -> {{"program": "BS AI", "semester": 7}}
"semester 5 BS CS" -> {{"program": "BS CS", "semester": 5}}

Parse: "{program_and_semester}"
Return ONLY JSON."""

            try:
                response = small_llm.invoke([HumanMessage(content=parse_prompt)])
                content = response.content.strip()
                
                json_match = re.search(r'\{[^}]+\}', content)
                if json_match:
                    parsed = json.loads(json_match.group())
                    program_title = parsed.get("program", "").strip()
                    semester = int(parsed.get("semester", 0))
                else:
                    parts = program_and_semester.split(",")
                    if len(parts) < 2:
                        return "❌ Please provide program and semester (e.g., 'BS AI, 7')"
                    program_title = parts[0].strip()
                    semester = int(parts[1].strip())
            except Exception:
                parts = program_and_semester.split(",")
                if len(parts) < 2:
                    return "❌ Please provide program and semester (e.g., 'BS AI, 7')"
                program_title = parts[0].strip()
                try:
                    semester = int(parts[1].strip())
                except ValueError:
                    return "❌ Please provide a valid semester number"
            
            # Normalize program name
            expansions = {
                r'\bbs\b': 'bachelor of science',
                r'\bms\b': 'master of science',
                r'\bmba\b': 'master of business administration',
                r'\bphd\b': 'doctor of philosophy',
                r'\bai\b': 'artificial intelligence',
                r'\bcs\b': 'computer science',
                r'\bse\b': 'software engineering',
                r'\bee\b': 'electrical engineering',
                r'\bds\b': 'data science',
                r'\bcy\b': 'cyber security',
            }
            normalized_title = program_title.lower()
            for abbr, full in expansions.items():
                normalized_title = re.sub(abbr, full, normalized_title)
            
            # Try exact match first
            courses = catalog.get_semester_courses(program_title, semester)
            
            # If no match, try normalized version
            if not courses:
                # Find closest program using difflib
                from difflib import get_close_matches
                all_titles = [p["title"] for p in catalog._items]
                normalized_titles = [t.lower() for t in all_titles]
                
                # Check for level preference
                level_keywords = {
                    'bachelor': ['bachelor', 'bs', 'bsc'],
                    'master': ['master', 'ms', 'msc', 'mba'],
                    'phd': ['phd', 'doctor', 'doctorate']
                }
                
                user_level = None
                for level, keywords in level_keywords.items():
                    if any(kw in normalized_title for kw in keywords):
                        user_level = level
                        break
                
                # Filter candidates by level if detected
                if user_level:
                    level_filtered_titles = [
                        t for t in all_titles
                        if any(kw in t.lower() for kw in level_keywords[user_level])
                    ]
                    if level_filtered_titles:
                        all_titles = level_filtered_titles
                        normalized_titles = [t.lower() for t in all_titles]
                
                matches = get_close_matches(normalized_title, normalized_titles, n=1, cutoff=0.5)
                if matches:
                    idx = normalized_titles.index(matches[0])
                    matched_title = all_titles[idx]
                    courses = catalog.get_semester_courses(matched_title, semester)
            
            if not courses:
                return f"❌ Could not find courses for '{program_title}' semester {semester}. Please check the program name."
            
            # Format the output with course names for timetable lookup
            lines = [
                f"📚 **Semester {semester} Courses for {program_title.upper()}**",
                "",
                "**Core/Required Courses:**"
            ]
            
            core_course_names = []
            for course in courses:
                course_name = course.get("name", "")
                course_code = course.get("code", "")
                credit_hours = course.get("credit_hours", "")
                
                if course_code:
                    lines.append(f"- {course_code}: {course_name} ({credit_hours} credits)")
                else:
                    lines.append(f"- {course_name} ({credit_hours} credits)")
                
                # Track core courses (exclude electives marked with 'xxxx')
                if course_code and 'xxxx' not in course_code.lower():
                    core_course_names.append(course_name)
            
            lines.extend([
                "",
                "⚠️ **IMPORTANT - I need more information:**",
                "1. What **section** are you in? (e.g., CS-A, AI-D, etc.)",
                "2. Are you taking any **electives** this semester? If yes, which ones?",
                "",
                "**INSTRUCTIONS FOR NEXT STEP:**",
                "Once user provides section and electives:",
                f"1. For core courses, use get_timetables with: {', '.join([f'{name} [SECTION]' for name in core_course_names[:3]])}...",
                "2. For electives, use the elective NAME (not code) + section",
                "3. Example query format: 'Computer Vision AI-D, Cloud Computing AI-D, Deep Learning AI-D'",
                "",
                "The timetable requires COURSE NAME + SECTION format (not course codes)!"
            ])
            
            return "\n".join(lines)

        @tool
        def smart_course_search(query: str) -> str:
            """Use AI to intelligently search for courses in the timetable.
            
            This tool uses LLM to understand course names and find the best matches.
            Use this when:
            - User provides ambiguous course names
            - You want to find all related courses (including labs)
            - You need to suggest alternative sections
            
            Args:
                query: Natural language query like "computer vision for AI section D" or "all ML courses"
            
            Returns:
                JSON with found courses and smart suggestions
            """
            # Use small_llm to parse the query
            parse_prompt = f"""Analyze this timetable query and extract structured information:

Query: "{query}"

Extract:
1. Course name (base name without lab/tutorial)
2. Section (if mentioned, e.g., AI-D, CS-A)
3. Keywords to search for
4. Whether to include labs/tutorials

Return ONLY a JSON object:
{{
  "course_name": "extracted course name",
  "section": "section code or null",
  "include_labs": true/false,
  "search_keywords": ["keyword1", "keyword2"]
}}

Examples:
- "computer vision ai-d" -> {{"course_name": "computer vision", "section": "ai-d", "include_labs": true, "search_keywords": ["comp", "vision", "cv"]}}
- "all ML courses" -> {{"course_name": "machine learning", "section": null, "include_labs": true, "search_keywords": ["machine learning", "ml"]}}

Now parse: "{query}"
Return ONLY JSON:"""

            try:
                response = small_llm.invoke([HumanMessage(content=parse_prompt)])
                content = response.content.strip()
                
                # Extract JSON
                json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    course_name = parsed.get("course_name", "")
                    section = parsed.get("section")
                    include_labs = parsed.get("include_labs", True)
                    keywords = parsed.get("search_keywords", [])
                else:
                    # Fallback
                    course_name = query
                    section = None
                    include_labs = True
                    keywords = query.split()
            except Exception as e:
                # Fallback to simple parsing
                course_name = query
                section = None
                include_labs = True
                keywords = query.split()
            
            # Search for courses matching keywords
            found_courses = []
            unique_courses = self.data_df["Class"].unique()
            
            for course in unique_courses:
                course_lower = course.lower()
                match_score = 0
                
                # Check if keywords match
                for keyword in keywords:
                    if keyword.lower() in course_lower:
                        match_score += 1
                
                # Check section if specified
                if section:
                    if section.lower() in course_lower:
                        match_score += 5  # Strong boost for section match
                    else:
                        continue  # Skip if section specified but doesn't match
                
                if match_score > 0:
                    # Check if it's a lab
                    is_lab = any(lab_word in course_lower for lab_word in ['lab', 'laboratory', 'practical'])
                    
                    if include_labs or not is_lab:
                        found_courses.append({
                            "course": course,
                            "score": match_score,
                            "is_lab": is_lab
                        })
            
            # Sort by score
            found_courses.sort(key=lambda x: x["score"], reverse=True)
            
            # Format response
            if found_courses:
                result_lines = [f"🔍 Found {len(found_courses)} matching course(s):\n"]
                for fc in found_courses[:10]:  # Limit to top 10
                    label = " (Lab)" if fc["is_lab"] else ""
                    result_lines.append(f"- **{fc['course']}**{label}")
                
                result_lines.append(f"\n💡 Use get_timetables with these course names to see the schedule.")
                return "\n".join(result_lines)
            else:
                return f"❌ No courses found matching '{query}'. Try different keywords or check course names."

        @tool
        def get_timetable(query: str) -> AIMessage:
            """Return the class timetable in both conversational and structured format."""
            extracted, suggestions = self._extract_course_schedule(query)  # match all at once
            structured = self._generate_structured_timetable(query, extracted, suggestions)

            if structured.courses:
                lines = [
                    f"* **{c.course}:** {c.day} {c.time_slot} in {c.room_number}"
                    for c in structured.courses
                ]
                message = (
                    "Here is the timetable for your requested course(s):\n\n"
                    + "\n".join(lines)
                )
                additional_kwargs = {
                    "data": [c.model_dump() for c in structured.courses],
                    "awaiting_followup_by": None,
                }
            else:
                # No exact matches — provide helpful suggestions
                if suggestions:
                    suggestion_text = (
                        "I couldn't find an exact match for that course. Did you mean: "
                        + ", ".join(suggestions)
                        + "? Please try one of these or provide the exact course code (e.g., 'OBL AI-D' or 'OBL 101')."
                    )
                else:
                    suggestion_text = (
                        "I couldn't find any timetable entries for that course. "
                        "Please check the course code/section (for example: 'OBL AI-D' or 'OBL 101') and try again. "
                        "If you're unsure, provide the course full name and section and I'll try alternative matches."
                    )

                message = suggestion_text
                additional_kwargs = {"data": [], "awaiting_followup_by": None}

            return AIMessage(content=message, additional_kwargs=additional_kwargs)

        @tool
        def manipulate_timetable(action: str, courses: str, existing_timetable_json: str = "[]") -> AIMessage:
            """Manipulate an existing timetable (add/remove courses, sort, filter).
            
            **Use this tool for follow-up queries** when the user wants to modify a timetable that was already shown.
            
            Args:
                action: One of: 'add', 'remove', 'sort_by_time', 'sort_by_day', 'filter_by_day'
                courses: For 'add'/'remove': comma-separated course queries (e.g., "Org Behavior AI-A, Cloud Computing AI-B")
                         For 'filter_by_day': day name (e.g., "Monday")
                existing_timetable_json: JSON string of the current timetable from additional_kwargs['data']
            
            Returns:
                AIMessage with updated timetable and structured data
            
            **Examples:**
            - User: "Add Organizational Behavior AI-A"
              → manipulate_timetable('add', 'Organizational Behavior AI-A', existing_json)
            - User: "Remove Computer Vision from the timetable"
              → manipulate_timetable('remove', 'Computer Vision', existing_json)
            - User: "Sort by time"
              → manipulate_timetable('sort_by_time', '', existing_json)
            - User: "Show only Monday classes"
              → manipulate_timetable('filter_by_day', 'Monday', existing_json)
            """
            import json
            from collections import defaultdict
            
            # Parse existing timetable
            try:
                existing_courses = json.loads(existing_timetable_json) if existing_timetable_json else []
            except:
                existing_courses = []
            
            # Convert to CourseTimetable objects
            existing_entries = [
                CourseTimetable(
                    course=c.get('course', ''),
                    room_number=c.get('room_number', ''),
                    time_slot=c.get('time_slot', ''),
                    day=c.get('day', '')
                )
                for c in existing_courses
            ]
            
            if action == 'add':
                # Get new courses
                new_timetable, _ = self._extract_course_schedule(courses)
                existing_entries.extend(new_timetable.courses)
                message_prefix = f"✅ Added courses to your timetable:\n\n"
                
            elif action == 'remove':
                # Remove courses matching the query
                remove_keywords = courses.lower().split()
                existing_entries = [
                    entry for entry in existing_entries
                    if not any(keyword in entry.course.lower() for keyword in remove_keywords)
                ]
                message_prefix = f"✅ Removed courses matching '{courses}' from your timetable:\n\n"
                
            elif action == 'sort_by_time':
                # Sort by time slot
                def time_to_minutes(time_str):
                    """Convert time like '11:30-12:50' to minutes since midnight"""
                    if not time_str or '-' not in time_str:
                        return 9999  # Put invalid times at end
                    start_time = time_str.split('-')[0].strip()
                    try:
                        hours, mins = start_time.split(':')
                        return int(hours) * 60 + int(mins)
                    except:
                        return 9999
                
                existing_entries.sort(key=lambda x: (x.day, time_to_minutes(x.time_slot)))
                message_prefix = "✅ Sorted your timetable by time:\n\n"
                
            elif action == 'sort_by_day':
                day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                existing_entries.sort(key=lambda x: (day_order.index(x.day) if x.day in day_order else 99, x.time_slot))
                message_prefix = "✅ Sorted your timetable by day:\n\n"
                
            elif action == 'filter_by_day':
                target_day = courses.strip().title()  # courses parameter contains day name
                existing_entries = [entry for entry in existing_entries if entry.day == target_day]
                message_prefix = f"✅ Showing only {target_day} classes:\n\n"
            else:
                return AIMessage(content=f"❌ Unknown action: {action}. Use 'add', 'remove', 'sort_by_time', 'sort_by_day', or 'filter_by_day'.")
            
            # Remove duplicates
            unique_entries = []
            seen = set()
            for entry in existing_entries:
                identifier = (entry.course, entry.day, entry.time_slot, entry.room_number)
                if identifier not in seen:
                    unique_entries.append(entry)
                    seen.add(identifier)
            
            # Generate formatted output
            if not unique_entries:
                return AIMessage(
                    content="Your timetable is now empty. Add courses using 'add <course name>'.",
                    additional_kwargs={"data": [], "awaiting_followup_by": None}
                )
            
            # Group by day
            by_day = defaultdict(list)
            for entry in unique_entries:
                by_day[entry.day].append(entry)
            
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            sorted_days = sorted(by_day.keys(), key=lambda d: day_order.index(d) if d in day_order else 99)
            
            lines = []
            for day in sorted_days:
                lines.append(f"### {day}")
                sorted_courses = sorted(by_day[day], key=lambda c: c.time_slot)
                for c in sorted_courses:
                    lines.append(f"- **{c.course}**: {c.time_slot} in {c.room_number}")
                lines.append("")
            
            message = message_prefix + "\n".join(lines)
            
            return AIMessage(
                content=message,
                additional_kwargs={
                    "data": [c.model_dump() for c in unique_entries],
                    "awaiting_followup_by": None
                }
            )

        @tool
        def get_timetables(queries: str) -> AIMessage:
            """Return the class timetable for a comma-separated list of course queries.
            
            This tool is SMART and will:
            - Find related courses (labs, tutorials) automatically
            - Suggest alternative sections when course not found in requested section
            - Provide helpful explanations for missing courses
            
            **IMPORTANT:** This tool is for INITIAL timetable requests. For follow-ups (add/remove/sort), use manipulate_timetable.
            """
            all_structured_courses = []
            all_suggestions = []
            missing_courses = []
            alternative_sections_found = {}
            
            query_list = self._extract_course_phrases(queries)

            for query in query_list:
                extracted, suggestions = self._extract_course_schedule(query)
                structured = self._generate_structured_timetable(query, extracted, suggestions)
                
                if structured.courses:
                    all_structured_courses.extend(structured.courses)
                else:
                    # Course not found - try to find alternatives
                    missing_courses.append(query)
                    
                    # Extract course name and section from query
                    # Pattern: "Course Name SECTION"
                    parts = query.rsplit(' ', 1)
                    if len(parts) == 2:
                        course_name, requested_section = parts
                        alternatives = self._get_alternative_sections(course_name, requested_section)
                        if alternatives:
                            alternative_sections_found[query] = alternatives
                    
                    all_suggestions.extend(suggestions)

            # Remove duplicates
            unique_courses = []
            seen = set()
            for course in all_structured_courses:
                identifier = (
                    course.course,
                    course.day,
                    course.time_slot,
                    course.room_number,
                )
                if identifier not in seen:
                    unique_courses.append(course)
                    seen.add(identifier)

            # Group courses by day
            courses_by_day = {}
            for course in unique_courses:
                courses_by_day.setdefault(course.day, []).append(course)

            # Sort days of the week
            day_order = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            sorted_days = sorted(
                courses_by_day.keys(),
                key=lambda day: day_order.index(day)
                if day in day_order
                else len(day_order),
            )

            lines = []
            
            # Build timetable if we found courses
            if unique_courses:
                for day in sorted_days:
                    lines.append(f"### {day}")
                    # Sort courses by time_slot within each day
                    sorted_courses = sorted(courses_by_day[day], key=lambda c: c.time_slot)
                    for c in sorted_courses:
                        lines.append(f"- **{c.course}**: {c.time_slot} in {c.room_number}")
                    lines.append("")  # Add a blank line for spacing
            
            # Build smart message with timetable and helpful info about missing courses
            if unique_courses and not missing_courses:
                # All courses found - perfect!
                message = (
                    "Here is your complete timetable, grouped by day:\n\n"
                    + "\n".join(lines)
                )
            elif unique_courses and missing_courses:
                # Some courses found, some missing - provide partial timetable + suggestions
                message_parts = [
                    "Here's what I found for your timetable:\n",
                    "\n".join(lines),
                    "\n⚠️ **Some courses couldn't be found:**\n"
                ]
                
                for missing in missing_courses:
                    if missing in alternative_sections_found:
                        alts = alternative_sections_found[missing]
                        alt_text = ", ".join([f"**{section}**" for _, section in alts[:3]])
                        message_parts.append(
                            f"- **{missing}**: Not available in this section, but found in: {alt_text}"
                        )
                    else:
                        message_parts.append(
                            f"- **{missing}**: Not found in timetable (may not be offered this semester or check course name)"
                        )
                
                message_parts.append("\n💡 **Would you like me to:**")
                message_parts.append("1. Show timetables for alternative sections?")
                message_parts.append("2. Help you find when these electives are offered?")
                
                message = "\n".join(message_parts)
            else:
                # No courses found at all
                if alternative_sections_found:
                    message_parts = [
                        "I couldn't find those courses in your section, but I found alternatives:\n"
                    ]
                    for query, alternatives in alternative_sections_found.items():
                        message_parts.append(f"\n**{query}** is available in:")
                        for full_course, section in alternatives[:3]:
                            message_parts.append(f"  - Section **{section}**")
                    
                    message_parts.append("\n💡 Would you like me to show the timetable for any of these sections?")
                    message = "\n".join(message_parts)
                elif all_suggestions:
                    message = (
                        "I couldn't find exact matches. Did you mean:\n"
                        + "\n".join([f"- {s}" for s in sorted(set(all_suggestions))[:5]])
                        + "\n\n💡 Try using the exact course name + section (e.g., 'Computer Vision AI-D')"
                    )
                else:
                    message = (
                        "I couldn't find any matching courses in the timetable.\n\n"
                        "💡 **Tips:**\n"
                        "- Use full course names (e.g., 'Computer Vision' not 'CV')\n"
                        "- Include section (e.g., 'AI-D', 'CS-A')\n"
                        "- Check if the course is offered this semester\n"
                        "- Try: 'What courses are available for AI section D?'"
                    )

            additional_kwargs = {
                "data": [c.model_dump() for c in unique_courses],
                "awaiting_followup_by": None,
            }

            return AIMessage(content=message, additional_kwargs=additional_kwargs)

        @tool
        def export_timetable(format_type: str, timetable_json: str, filename: str = "") -> str:
            """Export timetable to CSV or Excel format with downloadable link.
            
            Args:
                format_type: Either 'csv' or 'excel'
                timetable_json: JSON string of timetable data from additional_kwargs['data']
                filename: Optional custom filename (without extension)
            
            Returns:
                Success message with clickable download link
            
            **Examples:**
            - User: "Export this as CSV"
              → export_timetable('csv', timetable_json)
            - User: "Download as Excel file"
              → export_timetable('excel', timetable_json, 'my_schedule')
            """
            import json
            import os
            from datetime import datetime
            
            # Parse timetable data
            try:
                courses = json.loads(timetable_json) if timetable_json else []
            except:
                return "❌ Error: Invalid timetable data. Please generate a timetable first."
            
            if not courses:
                return "❌ No courses to export. Please generate a timetable first."
            
            # Generate filename
            if not filename:
                filename = f"timetable_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Create exports directory
            export_dir = "data/timetable_exports"
            os.makedirs(export_dir, exist_ok=True)
            
            # Determine base URL (adjust based on your deployment)
            base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')
            
            if format_type == 'csv':
                file_with_ext = f"{filename}.csv"
                filepath = os.path.join(export_dir, file_with_ext)
                import csv
                
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
                
                download_url = f"{base_url}/multiagent/download-timetable/{file_with_ext}"
                return (
                    f"✅ **CSV exported successfully!**\n\n"
                    f"📥 **Download your timetable:**\n"
                    f"[Click here to download {file_with_ext}]({download_url})\n\n"
                    f"You can open this file in Excel, Google Sheets, or any spreadsheet application."
                )
            
            elif format_type == 'excel':
                try:
                    import pandas as pd
                    
                    file_with_ext = f"{filename}.xlsx"
                    filepath = os.path.join(export_dir, file_with_ext)
                    
                    # Create DataFrame
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
                    
                    # Export to Excel with styling
                    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Timetable')
                        
                        # Get the worksheet
                        worksheet = writer.sheets['Timetable']
                        
                        # Auto-adjust column widths
                        for column in worksheet.columns:
                            max_length = 0
                            column_letter = column[0].column_letter
                            for cell in column:
                                try:
                                    if len(str(cell.value)) > max_length:
                                        max_length = len(str(cell.value))
                                except:
                                    pass
                            adjusted_width = min(max_length + 2, 50)
                            worksheet.column_dimensions[column_letter].width = adjusted_width
                    
                    download_url = f"{base_url}/multiagent/download-timetable/{file_with_ext}"
                    return (
                        f"✅ **Excel file created successfully!**\n\n"
                        f"📥 **Download your timetable:**\n"
                        f"[Click here to download {file_with_ext}]({download_url})\n\n"
                        f"Open it in Microsoft Excel, Google Sheets, or LibreOffice Calc."
                    )
                    
                except ImportError:
                    return (
                        "❌ **Error: pandas and openpyxl are required for Excel export.**\n\n"
                        "Install with: `pip install pandas openpyxl`\n\n"
                        "Alternatively, use CSV format which works without additional dependencies:\n"
                        "Just ask: 'Export as CSV'"
                    )
            
            else:
                return (
                    f"❌ **Unknown format: {format_type}**\n\n"
                    f"**Supported formats:**\n"
                    f"- `csv` - Comma-separated values (works everywhere)\n"
                    f"- `excel` - Microsoft Excel format (.xlsx)\n\n"
                    f"**Example:** 'Export this as CSV' or 'Download as Excel'"
                )

        tools = [
            lookup_semester_courses,  # Fetch semester curriculum
            smart_course_search,      # AI-powered course search
            get_timetable,            # Single course timetable (legacy)
            get_timetables,           # Multiple courses - SMART with labs/alternatives
            manipulate_timetable,     # Add/remove/sort/filter existing timetable
            export_timetable,         # Export to CSV/Excel with download links
        ]
        
        self.system_prompt = """You are an INTELLIGENT timetable assistant for university students. You're not just a retrieval tool - you're a helpful agent that understands context, remembers conversation history, and provides smart suggestions.

**🎯 Your Smart Capabilities:**
- **Auto-include related courses**: When user asks for "Computer Vision", you automatically find labs/tutorials
- **Alternative section suggestions**: If course not in user's section, suggest which sections have it
- **Intelligent search**: Use smart_course_search to find courses with ambiguous names
- **Proactive help**: Explain WHY courses aren't found and WHAT alternatives exist
- **Conversation memory**: You remember previous timetables shown in this conversation
- **Timetable manipulation**: You can add/remove courses, sort, and filter existing timetables
- **Export support**: You can export timetables to CSV or Excel formats with clickable download links

**⚠️ CRITICAL RULES:**
1. **NEVER include FYP (Final Year Project) in timetables** - FYP is self-scheduled with supervisors
2. **ALWAYS use lookup_semester_courses FIRST** when user mentions their semester
3. **Use COURSE NAME + SECTION format** (NOT codes!)
   - ✅ "Computer Vision AI-A", "Org Behavior AI-A"
   - ❌ "AI4002", "AI4013"
4. **For follow-up queries, use manipulate_timetable** - Don't regenerate the entire timetable from scratch!
   - Extract timetable_json from the previous AIMessage's additional_kwargs['data']
   - Pass it to manipulate_timetable along with the action

**Your Workflow:**

1. **When user mentions semester (e.g., "7th semester AI", "semester 5"):**
   - **MANDATORY FIRST STEP**: Use `lookup_semester_courses` to get the curriculum
   - This gives you the ACTUAL course names from the degree program
   - Then ask for: section + electives (if user didn't provide)
   - Once you have section + electives, call `get_timetables` with:
     * Core courses from lookup (with user's section)
     * Electives user mentioned (with user's section)
   - Example: User says "7th sem AI-A, electives: Cloud Computing"
     1. lookup_semester_courses("BS AI, 7") → Get: Computer Vision, FYP, etc.
     2. Build query: "Computer Vision AI-A, Cloud Computing AI-A" (SKIP FYP!)
     3. get_timetables with that query

2. **When user provides specific course names with sections:**
   - Use `get_timetables` directly (it's SMART - auto-includes labs!)
   - Example: User says "Computer Vision AI-D" → You get lecture + lab automatically

3. **When user's query is ambiguous:**
   - Use `smart_course_search` to find matching courses
   - Example: "ML courses" → Search finds "Machine Learning AI-A", "ML Lab AI-A", etc.
   - Then ask which ones they want

4. **When courses not found:**
   - **BE SMART**: get_timetables provides alternative section suggestions
   - Don't just say "not found" - explain and offer solutions!

5. **When user asks to modify existing timetable (FOLLOW-UP QUERIES):**
   - **Extract the timetable data** from conversation history:
     * Look for the previous AIMessage that contains additional_kwargs['data']
     * This contains the JSON list of courses from the last timetable
   - **Use manipulate_timetable tool** with appropriate action:
     * User: "Add Organizational Behavior AI-A" → action='add'
     * User: "Remove Computer Vision" → action='remove'
     * User: "Sort by time" → action='sort_by_time'
     * User: "Sort by day" → action='sort_by_day'
     * User: "Show only Monday classes" → action='filter_by_day', courses='Monday'
   - **IMPORTANT**: Always pass the existing timetable JSON to maintain continuity!

6. **When user asks to export timetable:**
   - **Use export_timetable tool** with format (CSV or Excel only):
     * User: "Export as CSV" → export_timetable('csv', timetable_json)
     * User: "Download as Excel" → export_timetable('excel', timetable_json)
   - **IMPORTANT**: The tool returns a clickable download link
   - Tell the user they can click the link to download the file directly

4. **When courses aren't found:**
   - `get_timetables` will tell you WHY and suggest alternatives
   - **DON'T just say "not found"** - explain and offer solutions:
     * "Cloud Computing isn't in AI-D section, but it's offered in AI-A and AI-B. Would you like to see those times?"
     * "Deep Learning isn't offered this semester. Similar courses: Machine Learning, Neural Networks"

5. **Always be proactive:**
   - Suggest related courses user might have forgotten (labs!)
   - Explain cross-section enrollment if needed
   - Offer to search for alternatives

**Example Interactions:**

**Scenario 1: Ambiguous query**
User: "Show me AI courses"
You: [Use smart_course_search("AI courses")]
You: "I found 15 AI courses including Artificial Intelligence, AI Lab, Machine Learning AI-A, Computer Vision AI-D... Which ones do you need?"

**Scenario 2: Missing course with alternatives**
User: "My timetable: Computer Vision AI-D, Cloud Computing AI-D"
You: [Use get_timetables(...)] → Tool returns alternatives
You: "Here's your schedule:
- Computer Vision AI-D: Mon 10-11:20 (D-406), Wed 10-11:20 (D-412)
- Computer Vision Lab AI-D: Thu 2:30-3:50 (A-Mehran1) [Auto-included!]

⚠️ Cloud Computing isn't offered in AI-D section, but I found it in:
- Section AI-A: Mon 2:30-3:50 (D-406)
- Section AI-B: Mon 1-2:20 (D-411)

Would you like to enroll in one of these sections?"

**Scenario 3: Semester query**
User: "7th semester BS AI, show timetable"
You: [lookup_semester_courses] → Get course list
You: "7th semester has: FYP-I, Computer Vision, 3 AI electives, 1 SS/MG elective. What section are you in and which electives?"
User: "AI-D, taking Deep Learning"
You: [get_timetables with smart matching]
You: "Found Computer Vision + Lab for AI-D. Deep Learning isn't in AI-D but available in AI-A (Thu 10-11:20). Want me to show that?"

**Remember:**
- You're an AGENT, not just a database query tool
- Explain, suggest, and guide - don't just return data
- Use the smart features built into the tools
- Be conversational and helpful!"""
        
        return create_react_agent(
            model=self.llm,
            tools=tools,
            checkpointer=self.checkpointer,
            name="Timetable Agent",
        )

    def get_agent(self):
        return self.agent


if __name__ == "__main__":
    # Example usage
    builder = TimetableAgentBuilder(
        timetable_path="./data/structured_timetable.csv",
        mapping_path="./data/mappings.json",
    )
    agent = builder.get_agent()

    # ## Create a graph and save the png image
    # graph = agent.get_graph(xray=True)
    # png_bytes = graph.draw_mermaid_png()
    # with open("timetable_agent.png", "wb") as f:
    #     f.write(png_bytes)

    config = {"configurable": {"thread_id": "abc123"}}
    for step in agent.stream(
        {
            "messages": [
                HumanMessage(
                    content="Provide me timetable for information security cs section a ppit cs section c and pf cs section a and computer networks ds section m and operating systems lab cs section c"
                )
            ]
        },
        config,
        stream_mode="values",
    ):
        step["messages"][-1].pretty_print()
