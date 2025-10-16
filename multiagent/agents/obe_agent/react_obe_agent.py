from __future__ import annotations
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
import os

root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from config import llm, embeddings
from multiagent.utils.clo_plo_mapper import CLOPLOMappingEngine
from multiagent.memory.retriever_manager import get_session_retriever
from multiagent.memory.session_context import get_current as _get_session_ctx
import logging


# Module-level context fallback for cases where thread-local session_context
# isn't available in the tool execution thread.
_CURRENT_USER_ID: Optional[int] = None
_CURRENT_SESSION_ID: Optional[str] = None


def set_current_context(user_id: Optional[int], session_id: Optional[str]) -> None:
    """Set process-level fallback context for OBE tools.

    This is used when tools execute in a different thread where thread-local
    session_context isn't visible. Use carefully; set just-in-time before agent runs.
    """
    global _CURRENT_USER_ID, _CURRENT_SESSION_ID
    _CURRENT_USER_ID = user_id
    _CURRENT_SESSION_ID = session_id


class OBEReactTooling:
    """Tool implementations backing the OBE ReAct agent."""

    def __init__(self):
        self.engine = CLOPLOMappingEngine(embeddings=embeddings)

    def map_clos_to_plos(self, clos: List[str], plos: List[str]) -> Dict[str, Any]:
        """Return top aligned PLOs for each CLO with composite scores and reasons.
        Inputs: clos: list[str], plos: list[str]
        Output JSON keys: mapping (per-CLO list), notes (summary)."""
        if not clos or not plos:
            return {"error": "Provide both CLOs and PLOs."}
        mapping = self.engine.generate_mapping(clos, plos, threshold=0.55, top_k=3)
        result: Dict[str, Any] = {"mapping": {}, "notes": []}
        for i, clo in enumerate(clos):
            rows = []
            for m in mapping.get(i, []):
                j = m["plo_index"]
                row = {
                    "clo_index": i,
                    "plo_index": j,
                    "score": round(m["scores"]["composite"], 2),
                    "bloom": m["clo_bloom"],
                    "verb_overlap": round(m["scores"].get("verb_overlap", 0.0), 2),
                }
                rows.append(row)
            result["mapping"][f"CLO_{i+1}"] = rows
            if not rows:
                result["notes"].append(
                    f"CLO {i+1} has weak alignment. Consider enriching verbs and domain cues."
                )
        return result

    def improve_or_enrich_clos(
        self, clos: List[str], target_plos: Optional[List[str]] = None
    ) -> List[str]:
        """Improve CLOs to strengthen alignment and measurability.
        Inputs: clos: list[str], target_plos (optional) to steer verbs and taxonomy.
        Returns: list[str] improved_clos."""
        if not clos:
            return []
        prompt = [
            "You are an OBE specialist. Improve these Course Learning Outcomes to be measurable and align strongly with CS program PLOs.",
            "- Use Bloom's action verbs at appropriate levels (apply/analyze/evaluate/design).",
            "- Keep domain specificity (e.g., stereo vision, segmentation, classification).",
            "- One capability per CLO; make success criteria observable where possible.",
        ]
        if target_plos:
            prompt.append("Target PLOs:\n" + "\n".join(target_plos))
        prompt.append("\nCLOs:\n" + "\n".join(f"- {c}" for c in clos))
        prompt.append(
            "\nReturn only the improved CLO list, one per line without numbering."
        )
        msg = "\n".join(prompt)
        out = llm.invoke(msg)
        lines = [l.strip(" -\t") for l in (out.content or "").splitlines() if l.strip()]
        # Keep 3-6 lines
        return lines[: max(3, min(6, len(lines)))]

    def explain_mapping_scores(self, clo: str, plo: str) -> str:
        """Explain why a CLO maps (or not) to a PLO using the engine's criteria."""
        info = self.engine.calculate_composite_score(clo, plo)
        parts = [
            f"Bloom alignment: {info['bloom_alignment']:.2f}",
            f"Verb overlap: {info['verb_overlap']:.2f}",
            f"Keyword similarity: {info['keyword_similarity']:.2f}",
            f"Semantic similarity: {info['semantic_similarity']:.2f}",
            f"Category factor: {info.get('category_factor', 1.0):.2f}",
            f"Composite: {info['composite']:.2f}",
        ]
        return "\n".join(parts)

    def extract_outcomes_from_session_docs(
        self,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        outcome_type: str = "both",
    ) -> Dict[str, Any]:
        """Extract CLOs/PLOs from uploaded documents in the current session.
        Returns {clos: list[str], plos: list[str]}."""
        logger = logging.getLogger(__name__)
        if user_id is None or session_id is None:
            uid, sid = _get_session_ctx()
            user_id = user_id if user_id is not None else uid
            session_id = session_id if session_id is not None else sid
        # Fallback to module-level context if still missing (cross-thread tool execution)
        if user_id is None or session_id is None:
            user_id = _CURRENT_USER_ID if user_id is None else user_id
            session_id = _CURRENT_SESSION_ID if session_id is None else session_id
        logger.info(
            f"[OBEReact] extract_outcomes_from_session_docs user_id={user_id}, session_id={session_id}"
        )
        retriever = (
            get_session_retriever(int(user_id), str(session_id))
            if (user_id is not None and session_id is not None)
            else None
        )
        if not retriever:
            logger.warning(
                f"[OBEReact] No retriever found for user_id={user_id}, session_id={session_id}"
            )
            return {
                "clos": [],
                "plos": [],
                "error": "No documents uploaded in this session.",
            }
        queries: List[str] = []
        if outcome_type in ("clo", "both"):
            queries.append(
                "course learning outcomes CLO objectives what students will learn"
            )
        if outcome_type in ("plo", "both"):
            queries.append(
                "program learning outcomes PLO program objectives competencies"
            )
        chunks = []
        for q in queries:
            try:
                hits = retriever.get_relevant_documents(q)
                logger.info(
                    f"[OBEReact] Retrieved {len(hits) if hits else 0} docs for query='{q}'"
                )
                chunks.extend(hits)
            except Exception:
                continue
        if not chunks:
            return {"clos": [], "plos": []}
        text = "\n\n".join([c.page_content for c in chunks[:10]])
        prompt = (
            "Extract CLOs and PLOs from the text.\n\nText:\n"
            + text
            + "\n\nReturn two sections titled 'CLOs:' and 'PLOs:' with bullet lists."
        )
        out = llm.invoke(prompt)
        content = (out.content or "").strip()
        import re

        def _pull(kind: str) -> List[str]:
            m = re.search(
                rf"{kind}s?:\s*(.*)$", content, flags=re.IGNORECASE | re.DOTALL
            )
            if not m:
                return []
            block = m.group(1)
            lines = re.findall(r"^[\-\*]\s*(.+)$", block, flags=re.MULTILINE)
            # Also handle numbered items
            lines = lines or re.findall(r"^\d+\.\s*(.+)$", block, flags=re.MULTILINE)
            return [
                re.sub(r"^(CLO|PLO)\s*\d+\s*:\s*", "", x, flags=re.IGNORECASE).strip()
                for x in lines
                if x.strip()
            ]

        return {"clos": _pull("CLO"), "plos": _pull("PLO")}

    def answer_from_session_docs(
        self,
        question: str,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Answer general questions from uploaded documents in this session (simple RAG)."""
        logger = logging.getLogger(__name__)
        if user_id is None or session_id is None:
            uid, sid = _get_session_ctx()
            user_id = user_id if user_id is not None else uid
            session_id = session_id if session_id is not None else sid
        # Fallback to module-level context if still missing
        if user_id is None or session_id is None:
            user_id = _CURRENT_USER_ID if user_id is None else user_id
            session_id = _CURRENT_SESSION_ID if session_id is None else session_id
        logger.info(
            f"[OBEReact] answer_from_session_docs user_id={user_id}, session_id={session_id}"
        )
        retriever = (
            get_session_retriever(int(user_id), str(session_id))
            if (user_id is not None and session_id is not None)
            else None
        )
        if not retriever:
            logger.warning(
                f"[OBEReact] No retriever found for user_id={user_id}, session_id={session_id}"
            )
            return "No session documents found."
        try:
            docs = retriever.get_relevant_documents(question)
            logger.info(
                f"[OBEReact] Retrieved {len(docs) if docs else 0} docs for question"
            )
        except Exception:
            docs = []
        ctx = "\n---\n".join([d.page_content for d in (docs or [])[:6]])
        if not ctx:
            return "NOT_FOUND_IN_DOCUMENTS"
        prompt = (
            "Use the context to answer. If not present, output ONLY NOT_FOUND_IN_DOCUMENTS.\n\n"
            + f"Context:\n{ctx}\n\nQuestion: {question}\nAnswer:"
        )
        out = llm.invoke(prompt)
        return (out.content or "").strip()


class OBEReactAgentBuilder:
    """Builds a ReAct agent for OBE mapping with in-pointer memory."""

    def __init__(self) -> None:
        self._agent = None

    def get_agent(self):
        if self._agent is not None:
            return self._agent
        tools = OBEReactTooling()
        # Persistent checkpointer so memory survives across processes (CLI runs)
        os.makedirs(os.path.join(root_dir, "data", "checkpoints"), exist_ok=True)
        db_path = os.path.join(root_dir, "data", "checkpoints", "obe_react.db")
        # Prefer SQLite persistent memory; fallback to in-memory if unavailable
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore

            memory = SqliteSaver.from_conn_string(f"sqlite:///{db_path}")
        except Exception:
            memory = MemorySaver()
        # Wrap methods as @tool functions to avoid 'self' in schemas
        t = tools

        @tool("map_clos_to_plos")
        def _map_clos_to_plos(clos: List[str], plos: List[str]) -> Dict[str, Any]:
            """Return per-CLO top PLO alignments with composite scores and brief notes.
            Inputs: clos: list[str], plos: list[str]."""
            return t.map_clos_to_plos(clos, plos)

        @tool("improve_or_enrich_clos")
        def _improve_or_enrich_clos(
            clos: List[str], target_plos: Optional[List[str]] = None
        ) -> List[str]:
            """Improve or enrich the provided CLOs to be measurable and align better with target PLOs.
            Inputs: clos: list[str], target_plos: optional list[str]. Returns improved CLO list.
            """
            return t.improve_or_enrich_clos(clos, target_plos)

        @tool("explain_mapping_scores")
        def _explain_mapping_scores(clo: str, plo: str) -> str:
            """Explain score components (Bloom, verbs, keywords, semantic, category factor, composite) for a CLO/PLO pair."""
            return t.explain_mapping_scores(clo, plo)

        @tool("extract_outcomes_from_session_docs")
        def _extract_outcomes_from_session_docs(
            user_id: Optional[int] = None,
            session_id: Optional[str] = None,
            outcome_type: str = "both",
        ) -> Dict[str, Any]:
            """Extract CLOs and/or PLOs from uploaded documents in a session. If user_id/session_id are omitted, the current chat context will be used."""
            return t.extract_outcomes_from_session_docs(
                user_id, session_id, outcome_type
            )

        @tool("answer_from_session_docs")
        def _answer_from_session_docs(
            question: str,
            user_id: Optional[int] = None,
            session_id: Optional[str] = None,
        ) -> str:
            """Answer general questions from the uploaded session documents using simple RAG. If user_id/session_id are omitted, the current chat context will be used."""
            return t.answer_from_session_docs(question, user_id, session_id)

        agent = create_react_agent(
            model=llm,
            tools=[
                _map_clos_to_plos,
                _improve_or_enrich_clos,
                _explain_mapping_scores,
                _extract_outcomes_from_session_docs,
                _answer_from_session_docs,
            ],
            checkpointer=memory,
        )
        self._agent = agent
        return agent


def run_obe_react(question: str, session_id: str = "default") -> str:
    try:
        builder = OBEReactAgentBuilder()
        agent = builder.get_agent()
    except Exception:
        return "OBE ReAct agent unavailable."

    final_answer = ""
    config = {"configurable": {"thread_id": f"obe_react::{session_id}"}}
    for step in agent.stream(
        {"messages": [HumanMessage(content=question)]}, config, stream_mode="values"
    ):
        if step.get("messages"):
            last = step["messages"][-1]
            if hasattr(last, "content") and isinstance(last.content, str):
                final_answer = last.content
    return final_answer or ""
