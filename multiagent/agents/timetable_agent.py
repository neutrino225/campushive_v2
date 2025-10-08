import pandas as pd
import re
import json
from typing import List, Tuple
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain.tools import tool
from rapidfuzz import fuzz
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
        self.checkpointer = MemorySaver()
        self.agent = self._build_agent()

    def _load_mappings(self, path: str) -> dict:
        with open(path, "r") as f:
            return json.load(f)

    def _normalize(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        text = text.lower()
        text = re.sub(r"\s+", " ", text)
        for k, v in self.mappings.items():
            text = text.replace(k, v)
        return text.strip()

    def _extract_course_phrases(self, query: str) -> List[str]:
        return [q.strip() for q in re.split(r"and|,|;|\n", query.lower()) if q.strip()]

    def _get_unique_courses(self) -> List[str]:
        return self.data_df["Class"].unique().tolist()

    def _fuzzy_match_courses(self, query: str, threshold: int = 70) -> List[str]:
        """Return a tuple (matched_courses, suggestion_list).

        matched_courses: list of exact/close matches (score >= threshold)
        suggestion_list: list of course names that are close but below threshold
        """
        matched = set()
        suggestions = []
        phrases = self._extract_course_phrases(query)
        unique_courses = self._get_unique_courses()

        for phrase in phrases:
            norm_phrase = self._normalize(phrase)
            # track best candidates for suggestions
            scored = []
            for course in unique_courses:
                score = fuzz.partial_ratio(norm_phrase, self._normalize(course))
                if score >= threshold:
                    matched.add(course)
                else:
                    scored.append((course, score))

            # if no exact-ish matches, collect top suggestion(s)
            if not any(fuzz.partial_ratio(norm_phrase, self._normalize(c)) >= threshold for c in unique_courses):
                scored.sort(key=lambda x: x[1], reverse=True)
                for course, score in scored[:3]:
                    # only suggest reasonably similar ones
                    if score >= max(40, threshold - 30):
                        suggestions.append(f"{course} ({score}%)")

        # deduplicate suggestions while preserving order
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            if s not in seen:
                unique_suggestions.append(s)
                seen.add(s)

        return list(matched), unique_suggestions

    def _extract_course_schedule(self, query: str) -> Tuple[CourseTimetableList, List[str]]:
        """Return (CourseTimetableList, suggestions).

        suggestions is a list of human-readable suggestion strings (may be empty).
        """
        matched_courses, suggestions = self._fuzzy_match_courses(query)
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
- Identify the exact course names mentioned in the query (e.g., "PF (CS-A)").
- For each matching course, return **all entries** for **all days** and time slots where it appears.
- Use the exact course names from the data provided.
- Output valid JSON in this format:

{format_instructions}

Do not explain anything. Just output valid JSON.
""",
            input_variables=["query", "filtered_courses"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )

    def _generate_structured_timetable(
        self, query: str, extracted: CourseTimetableList
    ) -> CourseTimetableList:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke(
            {"query": query, "filtered_courses": self._to_json_list(extracted)}
        )

    def _build_agent(self):
        @tool
        def get_timetable(query: str) -> AIMessage:
            """Return the class timetable in both conversational and structured format."""
            extracted, suggestions = self._extract_course_schedule(query)  # match all at once
            structured = self._generate_structured_timetable(query, extracted)

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
                structured = self._generate_structured_timetable(query, extracted)
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
