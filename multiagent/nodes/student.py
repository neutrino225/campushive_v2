import sys
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Literal
import pandas as pd

# Add the root directory to the Python path so we can import from root modules
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import add_messages
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.prompts import PromptTemplate

from ..prompts.student import student_router_prompt
from ..prompts.general import general_prompt
from ..prompts.degree_advisor import degree_advisor_prompt

from ..agents.general_agent import RAGEngine
from ..agents.degree_advisor_agent import DegreeAdvisorAgent, DegreeReactAgentBuilder
from vector_store_manager import VectorStoreType
from utils import normalize_university_query
from config import llm
from ..routing.classifiers import classify_student


class ConversationState(Dict[str, Any]):
    pass


_TIMETABLE_AGENT = None
_TIMETABLE_INIT_ATTEMPTED = False
_TIMETABLE_BUILDER = None

_DAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
_DAY_ALIASES = {
    "mon": "Monday",
    "monday": "Monday",
    "tue": "Tuesday",
    "tues": "Tuesday",
    "tuesday": "Tuesday",
    "wed": "Wednesday",
    "weds": "Wednesday",
    "wednesday": "Wednesday",
    "thu": "Thursday",
    "thur": "Thursday",
    "thurs": "Thursday",
    "thursday": "Thursday",
    "fri": "Friday",
    "friday": "Friday",
    "sat": "Saturday",
    "saturday": "Saturday",
    "sun": "Sunday",
    "sunday": "Sunday",
}


@dataclass(frozen=True)
class TimetableEntry:
    class_name: str
    course_key: str
    course_name: str
    program: str
    program_code: str
    batch: str
    section: str
    room: str
    time_slot: str
    day: str
    start_minutes: int
    end_minutes: int


def _timetable_data_paths() -> tuple[Path, Path]:
    return (
        root_dir / "data" / "structured_timetable.csv",
        root_dir / "data" / "mappings.json",
    )


def _timetable_unavailable_message() -> str:
    timetable_path, mapping_path = _timetable_data_paths()
    return (
        "Timetable service is unavailable because the required timetable dataset is missing. "
        f"Expected files: {timetable_path} and {mapping_path}. "
        "The general and faculty vector stores do not contain class schedule rows."
    )


class _FallbackTimetableAgent:
    def __init__(self, message: str):
        self.message = message

    def stream(self, inputs, config, stream_mode="values"):
        yield {"messages": [type("MockMessage", (), {"content": self.message})()]}


def _normalize_course_key(builder, text: str) -> str:
    cleaned = re.sub(r"\[[^\]]+\]", "", text or "")
    return builder._normalize(cleaned).strip()


def _extract_program_section_filters(builder, normalized_query: str) -> set[tuple[str, str]]:
    filters: set[tuple[str, str]] = set()

    for program, section in re.findall(r"\b(cs|ai|se|ds|cy)[\s\-]+([a-z])\b", normalized_query):
        filters.add((program.upper(), section.upper()))

    program_aliases = {
        "computer science": "CS",
        "artificial intelligence": "AI",
        "software engineering": "SE",
        "data science": "DS",
        "cyber security": "CY",
        "cybersecurity": "CY",
    }
    for label, code in program_aliases.items():
        for section in re.findall(rf"{re.escape(label)}\s+([a-z])\b", normalized_query):
            filters.add((code, section.upper()))

    return filters


def _parse_time_component(value: str) -> int:
    hour_text, minute_text = value.split(":")
    hour = int(hour_text)
    minute = int(minute_text)

    # Timetable data stores afternoon slots without AM/PM, e.g. 01:25 means 13:25.
    if 1 <= hour <= 7:
        hour += 12

    return hour * 60 + minute


def _parse_time_slot(time_slot: str) -> tuple[int, int]:
    if not time_slot or time_slot.lower() == "nan" or "-" not in str(time_slot):
        raise ValueError(f"Invalid time slot: {time_slot}")
    start_text, end_text = [part.strip() for part in str(time_slot).split("-", 1)]
    start_minutes = _parse_time_component(start_text)
    end_minutes = _parse_time_component(end_text)
    if end_minutes <= start_minutes:
        end_minutes += 12 * 60
    return start_minutes, end_minutes


def _extract_day_filters(normalized_query: str) -> set[str]:
    day_filters: set[str] = set()

    if re.search(r"\bweekdays?\b", normalized_query):
        day_filters.update(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])

    if re.search(r"\bweekends?\b", normalized_query):
        day_filters.update(["Saturday", "Sunday"])

    if re.search(r"\btoday\b", normalized_query):
        day_filters.add(datetime.now().strftime("%A"))

    for alias, day_name in _DAY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", normalized_query):
            day_filters.add(day_name)

    return day_filters


def _extract_course_requests(
    builder,
    normalized_query: str,
    alias_to_course: dict[str, str],
) -> list[dict[str, object]]:
    requests: list[dict[str, object]] = []
    phrases = re.split(r"\b(?:and)\b|,|;|\n", normalized_query)

    for phrase in phrases:
        cleaned_phrase = phrase.strip()
        if not cleaned_phrase:
            continue
        section_filters = _extract_program_section_filters(builder, cleaned_phrase)
        course_keys = _match_course_keys(_sanitize_query_for_course_matching(cleaned_phrase), alias_to_course)
        for course_key in course_keys:
            requests.append({
                "course_key": course_key,
                "section_filters": set(section_filters),
            })

    if requests:
        return requests

    # Fallback to the whole query when it contains a single request without clear separators.
    course_keys = _match_course_keys(_sanitize_query_for_course_matching(normalized_query), alias_to_course)
    section_filters = _extract_program_section_filters(builder, normalized_query)
    for course_key in course_keys:
        requests.append({
            "course_key": course_key,
            "section_filters": set(section_filters),
        })

    return requests


def _extract_recent_timetable_context(
    builder,
    conversation_history: list[str] | None,
) -> list[dict[str, object]]:
    if not conversation_history:
        return []

    alias_to_course: dict[str, str] | None = None
    for previous_question in reversed(conversation_history):
        normalized_question = builder._normalize(previous_question or "")
        if not normalized_question:
            continue
        if alias_to_course is None:
            alias_to_course = _build_alias_to_course(builder)
        requests = _extract_course_requests(builder, normalized_question, alias_to_course)
        if requests:
            return requests

    return []


def _build_alias_to_course(builder) -> dict[str, str]:
    df = builder.data_df
    course_keys = sorted(
        {
            _normalize_course_key(builder, str(value))
            for value in df["Course"].tolist()
        }
    )
    alias_to_course: dict[str, str] = {course_key: course_key for course_key in course_keys if course_key}

    for alias, mapped in builder.mappings.items():
        mapped_key = _normalize_course_key(builder, str(mapped))
        if mapped_key in alias_to_course:
            alias_to_course[builder._normalize(str(alias))] = mapped_key

    return alias_to_course


def _match_course_keys(normalized_query: str, alias_to_course: dict[str, str]) -> list[str]:
    matched_course_keys: list[str] = []

    for alias in sorted(alias_to_course.keys(), key=len, reverse=True):
        if not alias:
            continue
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized_query):
            matched_course_keys.append(alias_to_course[alias])

    return list(dict.fromkeys(matched_course_keys))


def _sanitize_query_for_course_matching(normalized_query: str) -> str:
    sanitized = re.sub(r"\b(cs|ai|se|ds|cy)\s+[a-z]\b", " ", normalized_query)
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized.strip()


def _build_timetable_entries(builder, filtered_df) -> list[TimetableEntry]:
    entries: list[TimetableEntry] = []

    for _, row in filtered_df.iterrows():
        course_name = str(row["Course"])
        class_name = str(row["Class"])
        try:
            start_minutes, end_minutes = _parse_time_slot(str(row["Time"]))
        except ValueError:
            continue
        entries.append(
            TimetableEntry(
                class_name=class_name,
                course_key=_normalize_course_key(builder, course_name),
                course_name=course_name,
                program=str(row["Program"]),
                program_code=str(row["ProgramCode"]).upper(),
                batch=str(row["Batch"]),
                section=str(row["Section"]).upper(),
                room=str(row["Room"]),
                time_slot=str(row["Time"]),
                day=str(row["Day"]),
                start_minutes=start_minutes,
                end_minutes=end_minutes,
            )
        )

    return entries


def _format_class_option(entry: TimetableEntry) -> str:
    return f"{entry.course_name} {entry.program_code}-{entry.section}"


def _build_clarification_message(entries: list[TimetableEntry], requested_course_keys: list[str]) -> str:
    by_course: dict[str, list[TimetableEntry]] = {}
    for entry in entries:
        by_course.setdefault(entry.course_key, []).append(entry)

    lines = [
        "I found timetable data, but the request is ambiguous because the course exists in multiple sections.",
        "Please specify the exact class for each course, for example:",
    ]

    for course_key in requested_course_keys:
        course_entries = by_course.get(course_key, [])
        if not course_entries:
            continue
        seen: set[str] = set()
        options: list[str] = []
        for entry in sorted(course_entries, key=lambda item: (item.program_code, item.section, item.batch)):
            label = _format_class_option(entry)
            if label not in seen:
                seen.add(label)
                options.append(label)
        if not options:
            continue
        display_name = course_entries[0].course_name
        lines.append(f"- {display_name}: {', '.join(options[:8])}")

    lines.append("Example query: 'Give me the weekly timetable for Operating Systems CS-A and COAL SE-B'.")
    return "\n".join(lines)


def _filter_timetable_for_requests(filtered_df, course_requests: list[dict[str, object]]):
    selections = []
    for request in course_requests:
        course_key = str(request["course_key"])
        section_filters = set(request["section_filters"])
        subset = filtered_df[filtered_df["__course_key"] == course_key]
        if section_filters:
            subset = subset[
                subset.apply(
                    lambda row: (str(row["ProgramCode"]).upper(), str(row["Section"]).upper()) in section_filters,
                    axis=1,
                )
            ]
        selections.append(subset)

    if not selections:
        return filtered_df.iloc[0:0]

    return pd.concat(selections, ignore_index=False).drop_duplicates()


def _format_conflicts(entries: list[TimetableEntry]) -> list[str]:
    conflicts: list[str] = []
    grouped: dict[str, list[TimetableEntry]] = {}

    for entry in entries:
        grouped.setdefault(entry.day, []).append(entry)

    for day in _DAY_ORDER:
        day_entries = sorted(grouped.get(day, []), key=lambda item: (item.start_minutes, item.end_minutes, item.class_name))
        for current, upcoming in zip(day_entries, day_entries[1:]):
            if upcoming.start_minutes < current.end_minutes:
                conflicts.append(
                    f"- {day}: {_format_class_option(current)} ({current.time_slot}) overlaps with "
                    f"{_format_class_option(upcoming)} ({upcoming.time_slot})"
                )

    return conflicts


def _format_timetable_plan(
    entries: list[TimetableEntry],
    requested_course_keys: list[str],
    requested_days: set[str],
    inherited_from_history: bool,
) -> str:
    if not entries:
        return ""

    grouped: dict[str, list[TimetableEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.day, []).append(entry)

    display_classes = list(dict.fromkeys(_format_class_option(entry) for entry in entries))
    header = "Here is your weekly timetable:"
    if requested_days:
        header = "Here is the timetable for the requested day(s):"

    lines = [header, ""]
    lines.append(f"Classes: {', '.join(display_classes)}")
    if inherited_from_history:
        lines.append("Using the classes from your recent timetable context.")
    lines.append("")

    for day in _DAY_ORDER:
        day_entries = grouped.get(day, [])
        if not day_entries:
            continue
        lines.append(day)
        for entry in sorted(day_entries, key=lambda item: (item.start_minutes, item.end_minutes, item.class_name)):
            lines.append(
                f"- {entry.time_slot}: {_format_class_option(entry)} in {entry.room}"
            )
        lines.append("")

    conflicts = _format_conflicts(entries)
    if conflicts:
        lines.append("Conflicts detected:")
        lines.extend(conflicts)

    return "\n".join(lines).strip()


def _route_student(state: ConversationState) -> Literal["general", "degree", "timetable", "done"]:
    q = (state.get("question") or "").lower()
    if not q.strip():
        return "done"
    # Use LLM classifier with keyword fallback
    return classify_student(q, llm)


def build_student_graph():
    graph = StateGraph(ConversationState)

    # Nodes
    # Build a general RAG engine via the centralized vector store manager
    general_prompt_template = PromptTemplate(
        input_variables=["context", "question"],
        template=(
            f"{general_prompt}\n\n"
            "Context:\n{context}\n\nQuestion: {question}\nAnswer:"
        ),
    )

    try:
        engine = RAGEngine.from_vector_store_manager(
            llm=llm,
            store_type=VectorStoreType.GENERAL,
            prompt=general_prompt_template,
            normalize_fn=normalize_university_query,
            debug=False,
            use_ensemble=True,
        )
    except Exception:
        engine = None

    try:
        # Prefer the tool-enabled LangGraph agent for degree advisory
        degree_builder = DegreeReactAgentBuilder()
        degree_agent = degree_builder.get_agent()
    except Exception:
        degree_agent = None

    timetable_agent = None

    def general_node(state: ConversationState, config: RunnableConfig = None) -> ConversationState:
        question = state.get("question", "")
        try:
            eng = engine or _get_engine()
            answer = eng.answer(question, stream=False)
            if not isinstance(answer, str) or not answer.strip():
                answer = f"I'm your general info assistant. Question: {question}"
            return {**state, "result": answer}
        except Exception as e:
            # Re-raise API errors immediately instead of falling back
            raise RuntimeError(f"General agent API error: {e}") from e

    def degree_node(state: ConversationState, config: RunnableConfig = None) -> ConversationState:
        question = state.get("question", "")
        session_id = state.get("session_id", "default")
        try:
            # If the ReAct agent is available, stream to get the final answer
            if degree_agent is not None:
                final_answer = ""
                config_dict = {"configurable": {"thread_id": f"student_degree::{session_id}"}}
                # include system prompt if available on the builder
                try:
                    sys_text = getattr(degree_builder, "system_prompt_text", "")
                except NameError:
                    sys_text = ""
                msgs = []
                if sys_text:
                    msgs.append(SystemMessage(content=sys_text))
                msgs.append(HumanMessage(content=question))
                for step in degree_agent.stream(
                    {"messages": msgs},
                    config_dict,
                    stream_mode="values",
                ):
                    if step.get("messages"):
                        last_msg = step["messages"][-1]
                        if hasattr(last_msg, "content") and isinstance(last_msg.content, str):
                            final_answer = last_msg.content
                answer = final_answer
            else:
                # Fallback to simple RAG agent
                d = _get_deg_simple()
                answer = d.invoke(question)
            if not isinstance(answer, str) or not answer.strip():
                answer = f"I'm your degree advisor assistant. Question: {question}"
            return {**state, "result": answer}
        except Exception as e:
            # Re-raise API errors immediately instead of falling back
            raise RuntimeError(f"Degree advisor API error: {e}") from e

    def timetable_node(state: ConversationState, config: RunnableConfig = None) -> ConversationState:
        question = state.get("question", "")
        try:
            answer = _answer_timetable_query(question)
            if not isinstance(answer, str) or not answer.strip():
                answer = f"I'm your timetable assistant. Question: {question}"
            return {**state, "result": answer}
        except Exception as e:
            # Re-raise API errors immediately instead of falling back
            raise RuntimeError(f"Timetable agent API error: {e}") from e
        if not isinstance(answer, str) or not answer.strip():
            answer = f"I'm your timetable assistant. Question: {question}"
        return {**state, "result": answer}

    def router_node(state: ConversationState, config: RunnableConfig = None) -> ConversationState:
        return state

    graph.add_node("router", router_node)
    graph.add_node("general", general_node)
    graph.add_node("degree", degree_node)
    graph.add_node("timetable", timetable_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _route_student, {
        "general": "general",
        "degree": "degree",
        "timetable": "timetable",
        "done": END,
    })
    graph.add_edge("general", END)
    graph.add_edge("degree", END)
    graph.add_edge("timetable", END)

    return graph.compile()


# Export compiled node
student_router_node = build_student_graph()


# Lazy singletons for direct routing helper
_ENGINE = None
_DEG_SIMPLE = None
_DEG_REACT = None


def _get_engine():
    global _ENGINE
    if _ENGINE is None:
        try:
            gp = PromptTemplate(
                input_variables=["context", "question"],
                template=(f"{general_prompt}\n\n" "Context:\n{context}\n\nQuestion: {question}\nAnswer:"),
            )
            _ENGINE = RAGEngine.from_vector_store_manager(
                llm=llm,
                store_type=VectorStoreType.GENERAL,
                prompt=gp,
                normalize_fn=normalize_university_query,
                debug=False,
                use_ensemble=True,
            )
        except Exception:
            class _FallbackEngine:
                def answer(self, q: str, stream: bool = False) -> str:
                    q = q or ""
                    return f"I'm your general info assistant. Question: {q}"
                def stream_answer(self, q: str):
                    q = q or ""
                    yield f"I'm your general info assistant. Question: {q}"
            _ENGINE = _FallbackEngine()
    return _ENGINE


def _get_deg_simple():
    global _DEG_SIMPLE
    if _DEG_SIMPLE is None:
        try:
            _DEG_SIMPLE = DegreeAdvisorAgent()
        except Exception:
            class _FallbackDeg:
                def invoke(self, q: str) -> str:
                    q = q or ""
                    return f"I'm your degree advisor assistant. Question: {q}"
            _DEG_SIMPLE = _FallbackDeg()
    return _DEG_SIMPLE


def _get_timetable_agent():
    global _TIMETABLE_AGENT, _TIMETABLE_INIT_ATTEMPTED

    if _TIMETABLE_AGENT is not None:
        return _TIMETABLE_AGENT

    if _TIMETABLE_INIT_ATTEMPTED:
        return _FallbackTimetableAgent(_timetable_unavailable_message())

    _TIMETABLE_INIT_ATTEMPTED = True

    try:
        from ..agents.timetable_agent import TimetableAgentBuilder

        timetable_path, mapping_path = _timetable_data_paths()
        builder = TimetableAgentBuilder(
            timetable_path=str(timetable_path),
            mapping_path=str(mapping_path),
        )
        _TIMETABLE_AGENT = builder.get_agent()
    except Exception:
        _TIMETABLE_AGENT = _FallbackTimetableAgent(_timetable_unavailable_message())

    return _TIMETABLE_AGENT


def _get_timetable_builder():
    global _TIMETABLE_BUILDER

    if _TIMETABLE_BUILDER is not None:
        return _TIMETABLE_BUILDER

    timetable_path, mapping_path = _timetable_data_paths()
    if not timetable_path.exists() or not mapping_path.exists():
        return None

    try:
        from ..agents.timetable_agent import TimetableAgentBuilder

        _TIMETABLE_BUILDER = TimetableAgentBuilder(
            timetable_path=str(timetable_path),
            mapping_path=str(mapping_path),
        )
    except Exception:
        _TIMETABLE_BUILDER = None

    return _TIMETABLE_BUILDER


def _answer_timetable_query(question: str, conversation_history: list[str] | None = None) -> str:
    builder = _get_timetable_builder()
    if builder is None:
        return _timetable_unavailable_message()

    try:
        normalized_query = builder._normalize(question)
        df = builder.data_df.copy()
        df["__course_key"] = df["Course"].map(lambda value: _normalize_course_key(builder, str(value)))

        alias_to_course = _build_alias_to_course(builder)
        course_requests = _extract_course_requests(builder, normalized_query, alias_to_course)
        day_filters = _extract_day_filters(normalized_query)

        inherited_from_history = False
        if not course_requests:
            history_requests = _extract_recent_timetable_context(builder, conversation_history)
            if history_requests:
                course_requests = history_requests
                inherited_from_history = True

        if not course_requests:
            return (
                "I couldn't identify the course name in your timetable query. "
                "Please try a course name like 'Operating Systems CS-A', 'COAL SE-B', or "
                "'weekly timetable for Operating Systems CS-A and COAL SE-B'."
            )

        matched_course_keys = [str(request["course_key"]) for request in course_requests]
        filtered = df[df["__course_key"].isin(matched_course_keys)]
        all_entries = _build_timetable_entries(builder, filtered)

        ambiguous_courses = []
        for request in course_requests:
            course_key = str(request["course_key"])
            section_filters = set(request["section_filters"])
            if section_filters:
                continue
            class_options = {
                entry.class_name
                for entry in all_entries
                if entry.course_key == course_key
            }
            if len(class_options) > 1:
                ambiguous_courses.append(course_key)

        if ambiguous_courses:
            ambiguous_entries = [entry for entry in all_entries if entry.course_key in ambiguous_courses]
            requested_ambiguous_keys = [course_key for course_key in matched_course_keys if course_key in ambiguous_courses]
            return _build_clarification_message(ambiguous_entries, requested_ambiguous_keys)

        filtered = _filter_timetable_for_requests(filtered, course_requests)

        if day_filters:
            filtered = filtered[filtered["Day"].isin(day_filters)]

        if filtered.empty:
            requested = ", ".join(sorted(set(matched_course_keys)))
            requested_sections = sorted(
                {
                    f"{program}-{section}"
                    for request in course_requests
                    for program, section in set(request["section_filters"])
                }
            )
            if requested_sections:
                return (
                    f"I found timetable data for {requested}, but not for the requested section(s): {', '.join(requested_sections)}. "
                    "Please check the section code and try again."
                )
            if day_filters:
                requested_days = ", ".join(day for day in _DAY_ORDER if day in day_filters)
                return (
                    f"I found timetable data for {requested}, but there are no classes on {requested_days}. "
                    "Try another day or ask for the full weekly timetable."
                )
            return (
                f"I couldn't find timetable entries for {requested}. "
                "Please try the course with a section, for example 'OS CS-A' or 'COAL SE-B'."
            )

        entries = _build_timetable_entries(builder, filtered)
        return _format_timetable_plan(entries, matched_course_keys, day_filters, inherited_from_history)
    except Exception as e:
        return f"Timetable lookup failed: {e}"


def run_student(question: str, session_id: str = "default") -> str:
    """Direct runner (non-graph) for student routing to ensure deterministic test behavior."""
    state: ConversationState = {"question": question, "session_id": session_id}
    route = _route_student(state)
    if route == "degree":
        try:
            # Try ReAct agent first
            try:
                builder = DegreeReactAgentBuilder()
                agent = builder.get_agent()
            except Exception:
                agent = None
            if agent is not None:
                final_answer = ""
                config_dict = {"configurable": {"thread_id": f"student_degree_direct::{session_id}"}}
                # builder is local here; include its system prompt before user message
                sys_text = getattr(builder, "system_prompt_text", "")
                msgs = []
                if sys_text:
                    msgs.append(SystemMessage(content=sys_text))
                msgs.append(HumanMessage(content=question))
                for step in agent.stream(
                    {"messages": msgs},
                    config_dict,
                    stream_mode="values",
                ):
                    if step.get("messages"):
                        last_msg = step["messages"][-1]
                        if hasattr(last_msg, 'content') and isinstance(last_msg.content, str):
                            final_answer = last_msg.content
                ans = final_answer
            else:
                ans = _get_deg_simple().invoke(question)
            if not isinstance(ans, str) or not ans.strip():
                ans = f"I'm your degree advisor assistant. Question: {question}"
            return ans
        except Exception as e:
            # Re-raise API errors immediately instead of falling back
            raise RuntimeError(f"Degree advisor API error: {e}") from e
    if route == "general":
        try:
            ans = _get_engine().answer(question, stream=False)
            if not isinstance(ans, str) or not ans.strip():
                ans = f"I'm your general info assistant. Question: {question}"
            return ans
        except Exception as e:
            # Re-raise API errors immediately instead of falling back
            raise RuntimeError(f"General agent API error: {e}") from e
    if route == "timetable":
        try:
            ans = _answer_timetable_query(question)
        except Exception:
            ans = ""
        if not isinstance(ans, str) or not ans.strip():
            ans = f"I'm your timetable assistant. Question: {question}"
        return ans
    return ""


def run_student_streaming(question: str, session_id: str = "default"):
    """Direct runner with streaming enabled for student routing. Yields chunks."""
    state: ConversationState = {"question": question, "session_id": session_id}
    route = _route_student(state)
    if route == "degree":
        try:
            # Stream via ReAct degree agent when possible
            try:
                builder = DegreeReactAgentBuilder()
                agent = builder.get_agent()
            except Exception:
                agent = None
            if agent is not None:
                final_answer = ""
                config_dict = {"configurable": {"thread_id": f"student_degree_streaming::{session_id}"}}
                # builder is local here; include its system prompt before user message
                sys_text = getattr(builder, "system_prompt_text", "")
                msgs = []
                if sys_text:
                    msgs.append(SystemMessage(content=sys_text))
                msgs.append(HumanMessage(content=question))
                for step in agent.stream(
                    {"messages": msgs},
                    config_dict,
                    stream_mode="values",
                ):
                    if step.get("messages"):
                        last_msg = step["messages"][-1]
                        if hasattr(last_msg, 'content') and isinstance(last_msg.content, str):
                            final_answer = last_msg.content
                ans = final_answer
            else:
                ans = _get_deg_simple().invoke(question)
            if not isinstance(ans, str) or not ans.strip():
                ans = f"I'm your degree advisor assistant. Question: {question}"
            yield ans
        except Exception as e:
            # Re-raise API errors immediately instead of falling back
            raise RuntimeError(f"Degree advisor API error: {e}") from e
    elif route == "general":
        try:
            for chunk in _get_engine().stream_answer(question):
                yield chunk
        except Exception as e:
            # Re-raise API errors immediately instead of falling back
            raise RuntimeError(f"General agent API error: {e}") from e
    elif route == "timetable":
        try:
            ans = _answer_timetable_query(question)
            if not isinstance(ans, str) or not ans.strip():
                ans = f"I'm your timetable assistant. Question: {question}"
            yield ans
        except Exception as e:
            # Re-raise API errors immediately instead of falling back
            raise RuntimeError(f"Timetable agent API error: {e}") from e
    else:
        yield ""


def run_general(question: str) -> str:
    """Direct runner for general info agent."""
    try:
        ans = _get_engine().answer(question, stream=True)
        if not isinstance(ans, str) or not ans.strip():
            ans = f"I'm your general info assistant. Question: {question}"
        return ans
    except Exception as e:
        # Re-raise API errors immediately instead of falling back
        raise RuntimeError(f"General agent API error: {e}") from e
