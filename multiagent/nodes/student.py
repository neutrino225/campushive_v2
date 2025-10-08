import sys
from pathlib import Path
from typing import Dict, Any, Literal

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
from ..agents.timetable_agent import TimetableAgentBuilder
from vector_store_manager import VectorStoreType
from utils import normalize_university_query
from config import llm
from ..routing.classifiers import classify_student


class ConversationState(Dict[str, Any]):
    pass


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

    try:
        timetable_builder = TimetableAgentBuilder(
            timetable_path=str(root_dir / "data" / "structured_timetable.csv"),
            mapping_path=str(root_dir / "data" / "mappings.json"),
        )
        timetable_agent = timetable_builder.get_agent()
    except Exception as e:
        print(f"Error creating timetable agent: {e}")
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
        session_id = state.get("session_id", "default")
        try:
            agent = timetable_agent or _get_timetable_agent()
            # Since it's a langgraph agent, we need to stream it
            final_answer = ""
            config_dict = {"configurable": {"thread_id": f"student_timetable::{session_id}"}}
            for step in agent.stream(
                {"messages": [HumanMessage(content=question)]},
                config_dict,
                stream_mode="values",
            ):
                if step["messages"]:
                    last_msg = step["messages"][-1]
                    if hasattr(last_msg, 'content') and isinstance(last_msg.content, str):
                        final_answer = last_msg.content
            answer = final_answer
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
    try:
        from ..agents.timetable_agent import TimetableAgentBuilder
        builder = TimetableAgentBuilder(
            timetable_path=str(root_dir / "data" / "structured_timetable.csv"),
            mapping_path=str(root_dir / "data" / "mappings.json"),
        )
        return builder.get_agent()
    except Exception as e:
        print(f"Error in _get_timetable_agent: {e}")
        class _FallbackTimetable:
            def stream(self, inputs, config, stream_mode="values"):
                # Mock stream that yields a message
                yield {"messages": [type('MockMessage', (), {'content': f"I'm your timetable assistant. Question: {inputs['messages'][0].content}"})()]}
        return _FallbackTimetable()


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
            agent = _get_timetable_agent()
            final_answer = ""
            config_dict = {"configurable": {"thread_id": f"student_timetable_direct::{session_id}"}}
            for step in agent.stream(
                {"messages": [HumanMessage(content=question)]},
                config_dict,
                stream_mode="values",
            ):
                if step["messages"]:
                    last_msg = step["messages"][-1]
                    if hasattr(last_msg, 'content') and isinstance(last_msg.content, str):
                        final_answer = last_msg.content
            ans = final_answer
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
            agent = _get_timetable_agent()
            final_answer = ""
            config_dict = {"configurable": {"thread_id": f"student_timetable_streaming::{session_id}"}}
            for step in agent.stream(
                {"messages": [HumanMessage(content=question)]},
                config_dict,
                stream_mode="values",
            ):
                if step["messages"]:
                    last_msg = step["messages"][-1]
                    if hasattr(last_msg, 'content') and isinstance(last_msg.content, str):
                        final_answer = last_msg.content
            ans = final_answer
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
