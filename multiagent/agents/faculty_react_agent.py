from __future__ import annotations
import re
from typing import Callable, List

from langchain.agents import Tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage

from .faculty_agent import FacultyAgent, _faculty_display_name
from config import llm


class FacultyReactAgentBuilder:
    """Builds a LangGraph ReAct agent for faculty QA with structured tools.

    Tools include:
      - get_faculty_email
      - get_faculty_publications
      - get_faculty_education
      - get_faculty_experience
      - get_faculty_designation
      - get_faculty_department
      - get_faculty_extension
      - get_faculty_website
      - get_faculty_hec_status
      - get_faculty_summary
      - get_faculty_full_profile
      - faculty_search (semantic fallback over faculty corpus)

    Notes:
    - Tools accept a single string input. For summary/full profile, pass the person name.
    - "faculty_search" accepts a full question string and returns an answer via semantic retrieval.
    """

    def __init__(self):
        self.fac = FacultyAgent(debug=False)
        self.checkpointer = MemorySaver()
        self.agent = self._build_agent()

    def _wrap(self, fn: Callable[[str], str], name: str, description: str) -> Tool:
        return Tool(name=name, func=fn, description=description)

    def _build_agent(self):
        fac = self.fac

        # Person-resolving wrappers for one-arg tool signatures
        def _resolve_and(fn_person: Callable[[dict], str], fallback_msg: str = ""):
            def inner(person_name: str) -> str:
                p = fac._resolve_person(person_name)
                if not p:
                    return fallback_msg or "NOT_FOUND_IN_DOCUMENTS"
                out = fn_person(p)
                return out or (fallback_msg or "NOT_FOUND_IN_DOCUMENTS")
            return inner

        tools: List[Tool] = [
            self._wrap(
                _resolve_and(fac._tool_email, "Email not available."),
                name="get_faculty_email",
                description="Return the email address of the specified faculty member. Input: Person name.",
            ),
            self._wrap(
                _resolve_and(fac._tool_publications, "No publications available."),
                name="get_faculty_publications",
                description="Return a numbered list of publications for the faculty member. Input: Person name.",
            ),
            self._wrap(
                _resolve_and(fac._tool_education, "No education records available."),
                name="get_faculty_education",
                description="Return the education history as bullet points. Input: Person name.",
            ),
            self._wrap(
                _resolve_and(fac._tool_experience, "No experience records available."),
                name="get_faculty_experience",
                description="Return the work experience as bullet points. Input: Person name.",
            ),
            self._wrap(
                _resolve_and(fac._tool_designation, "Designation not available."),
                name="get_faculty_designation",
                description="Return the current designation/title. Input: Person name.",
            ),
            self._wrap(
                _resolve_and(fac._tool_department, "Department not available."),
                name="get_faculty_department",
                description="Return the department. Input: Person name.",
            ),
            self._wrap(
                _resolve_and(fac._tool_extension, "Extension not available."),
                name="get_faculty_extension",
                description="Return the phone extension, if available. Input: Person name.",
            ),
            self._wrap(
                _resolve_and(fac._tool_website, "Website not available."),
                name="get_faculty_website",
                description="Return the personal or official website URL, if available. Input: Person name.",
            ),
            self._wrap(
                _resolve_and(fac._tool_hec_supervisor, "HEC supervisor status not available."),
                name="get_faculty_hec_status",
                description="Return whether the person is an HEC-recognized PhD supervisor (Yes/No). Input: Person name.",
            ),
            self._wrap(
                lambda person_name: (fac._generate_person_summary(fac._resolve_person(person_name), f"Provide a concise factual summary of {person_name}.", stream=False) if fac._resolve_person(person_name) else "NOT_FOUND_IN_DOCUMENTS"),
                name="get_faculty_summary",
                description="Return a concise generated summary paragraph for the person. Input: Person name.",
            ),
            self._wrap(
                lambda person_name: (fac._render_full_profile(fac._resolve_person(person_name)) if fac._resolve_person(person_name) else "NOT_FOUND_IN_DOCUMENTS"),
                name="get_faculty_full_profile",
                description="Return full profile (markdown) including education, experience, publications. Input: Person name.",
            ),
            # Semantic fallback for arbitrary faculty questions
            self._wrap(
                lambda question: fac.semantic_answer(question, stream=False),
                name="faculty_search",
                description="Answer a faculty-related question via semantic retrieval over the faculty corpus. Input: Full question.",
            ),
        ]

        return create_react_agent(
            model=llm,
            tools=tools,
            checkpointer=self.checkpointer,
            name="Faculty Agent",
        )

    def get_agent(self):
        return self.agent

    def stream(self, question: str):
        config = {"configurable": {"thread_id": "faculty_react"}}
        for step in self.agent.stream(
            {"messages": [HumanMessage(content=question)]},
            config,
            stream_mode="values",
        ):
            if step.get("messages"):
                last_msg = step["messages"][-1]
                if hasattr(last_msg, "content") and isinstance(last_msg.content, str):
                    yield last_msg.content


# Helper to expose a compiled graph-like object for image export
def build_faculty_react_graph():
    return FacultyReactAgentBuilder().get_agent()


# Export for importers (optional)
faculty_react_graph = build_faculty_react_graph()
