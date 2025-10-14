import pandas as pd
import re
import json
from typing import List, Tuple, Set
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

from config import llm

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
        # Removed MemorySaver - conversation context now passed via messages from wrapper
        
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

        # Handle parentheses and brackets
        text = re.sub(r"[\(\)\[\]]", " ", text)

        # Handle common abbreviations
        # Note: We need to be careful with order - do contractions before expansions
        # to avoid double-replacement issues
        
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
        # Normalize the query first
        normalized_query = self._normalize(query)

        # Split by common separators but keep them for context
        parts = re.split(r'(\band\b|,|;|\n)', normalized_query)

        # Filter out the separators and empty strings
        phrases = [p.strip() for p in parts if p.strip() and p not in ["and", ",", ";", "\n"]]

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

    def _fuzzy_match_courses(self, query: str, threshold: int = 60) -> Tuple[Set[str], List[str]]:
        """Enhanced fuzzy matching using multiple strategies."""
        matched = set()
        suggestions = []
        phrases = self._extract_course_phrases(query)
        unique_courses = self._get_unique_courses()

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

    def _extract_course_schedule(self, query: str) -> Tuple[CourseTimetableList, List[str]]:
        """Return (CourseTimetableList, suggestions) with improved course extraction."""
        # Extract phrases using the enhanced method
        phrases = self._extract_course_phrases(query)

        # Recognize course patterns in each phrase
        course_candidates = []
        for phrase in phrases:
            patterns = self._recognize_course_patterns(phrase)
            course_candidates.extend(patterns)

        # Use fuzzy matching on the candidates
        matched_courses, suggestions = self._fuzzy_match_courses(" ".join(course_candidates))

        # If no matches found, try with individual phrases
        if not matched_courses and course_candidates:
            for candidate in course_candidates:
                matches, suggs = self._fuzzy_match_courses(candidate)
                matched_courses.update(matches)
                suggestions.extend(suggs)

        filtered_df = self.data_df[self.data_df["Class"].isin(matched_courses)]
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
        def get_timetables(queries: str) -> AIMessage:
            """Return the class timetable for a comma-separated list of course queries."""
            all_structured_courses = []
            all_suggestions = []
            query_list = self._extract_course_phrases(queries)

            for query in query_list:
                extracted, suggestions = self._extract_course_schedule(query)
                structured = self._generate_structured_timetable(query, extracted, suggestions)
                all_structured_courses.extend(structured.courses)
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
            for day in sorted_days:
                lines.append(f"### {day}")
                # Sort courses by time_slot within each day
                sorted_courses = sorted(courses_by_day[day], key=lambda c: c.time_slot)
                for c in sorted_courses:
                    lines.append(f"- **{c.course}**: {c.time_slot} in {c.room_number}")
                lines.append("")  # Add a blank line for spacing

            message = (
                "Here is the consolidated timetable for your requested courses, grouped by day:\n\n"
                + "\n".join(lines)
            )

            # If there were queries with no matches, append suggestions
            if not unique_courses and all_suggestions:
                message = (
                    "I couldn't find exact matches for the courses you asked. "
                    "Did you mean: "
                    + ", ".join(sorted(set(all_suggestions)))
                    + "?"
                )

            additional_kwargs = {
                "data": [c.model_dump() for c in unique_courses],
                "awaiting_followup_by": None,
            }

            return AIMessage(content=message, additional_kwargs=additional_kwargs)

        tools = [
            Tool(
                name="get_timetable",
                func=get_timetable,
                description="Get timetable info for a single course.",
            ),
            Tool(
                name="get_timetables",
                func=get_timetables,
                description="Get timetable info for a list of courses.",
            ),
        ]
        return create_react_agent(
            model=self.llm,
            tools=tools,
            # No checkpointer - stateless agent receives context via messages
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
