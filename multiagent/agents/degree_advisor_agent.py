import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

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


class DegreeVectorStore:
    """Thin wrapper to get a retriever for degree programs."""

    def __init__(self):
        self.manager = VectorStoreManager(embeddings=embeddings)

    def get_retriever(self, k: int = 15):
        # The manager already returns an ensemble retriever when requested
        return self.manager.get_retriever(VectorStoreType.DEGREE_PROGRAMS, use_ensemble=True)


class DegreeCatalog:
    """Direct JSON-backed catalog for degree programs with fast filters.

    Expected file: data/degree_programs/degree_programs.json
    Each entry should include fields like title, level, field, duration_years, total_credit_hours, admission, etc.
    """

    def __init__(self, json_path: Optional[Path] = None):
        self.path = json_path or (root_dir / "data" / "degree_programs" / "degree_programs.json")
        self._items: List[Dict[str, Any]] = []
        self._index_by_title: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Normalize to list
                self._items = data if isinstance(data, list) else data.get("programs", [])
                # Title index
                self._index_by_title = {
                    str(item.get("title", "")).strip().lower(): item for item in self._items
                }
        except Exception:
            # Keep empty on failure; hybrid tools will still use vector search
            self._items = []
            self._index_by_title = {}

    # ---- JSON queries ----
    def by_field(self, field: str, limit: int = 20) -> List[Dict[str, Any]]:
        f = (field or "").strip().lower()
        if not f:
            return []
        out = [it for it in self._items if f in str(it.get("field", "")).lower() or f in str(it.get("title", "")).lower()]
        return out[:limit]

    def by_level(self, level: str, limit: int = 30) -> List[Dict[str, Any]]:
        lv = (level or "").strip().lower()
        if not lv:
            return []
        out = [it for it in self._items if lv in str(it.get("level", "")).lower()]
        return out[:limit]

    def details(self, title: str) -> Optional[Dict[str, Any]]:
        t = (title or "").strip().lower()
        if not t:
            return None
        # exact title first
        it = self._index_by_title.get(t)
        if it:
            return it
        # fuzzy contains
        for item in self._items:
            if t in str(item.get("title", "")).lower():
                return item
        return None

    def search(self, query: str, limit: int = 30) -> List[Dict[str, Any]]:
        q = (query or "").strip().lower()
        if not q:
            return []
        hits: List[Dict[str, Any]] = []
        for it in self._items:
            hay = " ".join(
                [
                    str(it.get("title", "")),
                    str(it.get("field", "")),
                    str(it.get("level", "")),
                    str(it.get("summary", "")),
                    str(it.get("curriculum", "")),
                    str(it.get("admission", "")),
                ]
            ).lower()
            if q in hay:
                hits.append(it)
        return hits[:limit]


def _format_program_line(p: Dict[str, Any]) -> str:
    title = p.get("title", "Unknown Title")
    level = p.get("level", "")
    field = p.get("field", "")
    duration = p.get("duration_years", p.get("duration", "N/A"))
    credits = p.get("total_credit_hours", p.get("credits", ""))
    tail = []
    if duration:
        tail.append(f"{duration} yrs")
    if credits:
        tail.append(f"{credits} credits")
    tail_str = f" ({', '.join(tail)})" if tail else ""
    lead = f"- {title}"
    if level or field:
        lead += f" [{level or 'Level N/A'} | {field or 'Field N/A'}]"
    return lead + tail_str


def _format_details(p: Dict[str, Any]) -> str:
    if not p:
        return "No details available."
    parts = []
    parts.append(f"Title: {p.get('title', 'N/A')}")
    parts.append(f"Level: {p.get('level', 'N/A')}")
    parts.append(f"Field: {p.get('field', 'N/A')}")
    if p.get("duration_years") or p.get("duration"):
        parts.append(f"Duration: {p.get('duration_years', p.get('duration', 'N/A'))} years")
    if p.get("total_credit_hours") or p.get("credits"):
        parts.append(f"Credit Hours: {p.get('total_credit_hours', p.get('credits', 'N/A'))}")
    if p.get("admission"):
        parts.append(f"Admission: {p.get('admission')}")
    if p.get("curriculum"):
        parts.append(f"Curriculum: {p.get('curriculum')}")
    if p.get("career_opportunities"):
        parts.append(f"Careers: {p.get('career_opportunities')}")
    if p.get("specializations"):
        parts.append(f"Specializations: {p.get('specializations')}")
    if p.get("tuition"):
        parts.append(f"Tuition: {p.get('tuition')}")
    return "\n".join(parts)


# ---------------- Tool-enabled LangGraph Agent ---------------- #

class DegreeReactAgentBuilder:
    """Builds a LangGraph ReAct agent for degree advisory with hybrid (JSON + vector) tools.

    Tools:
      - degree_by_field
      - degree_by_level
      - degree_details
      - degree_compare
      - degree_recommend
      - degree_search_semantic
      - degree_search_hybrid
      - ask_human (lightweight hook to involve a human when needed)
    """

    def __init__(self):
        self.catalog = DegreeCatalog()
        self.retriever = DegreeVectorStore().get_retriever(k=20)
        self.checkpointer = MemorySaver()  # keeps thread memory for human-in-the-loop continuity
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
        # Accept input such as "AI; level=BS" or just "Artificial Intelligence"
        raw = (text or "").strip()
        level = ""
        if ";" in raw and "level=" in raw.lower():
            try:
                left, right = raw.split(";", 1)
                raw = left.strip()
                kv = right.split("=", 1)
                if len(kv) == 2 and kv[0].strip().lower() == "level":
                    level = kv[1].strip()
            except Exception:
                pass

        # Detect implicit undergraduate intent from the raw query
        raw_l = raw.lower()
        undergrad_intent = False
        if any(tok in raw_l for tok in ["bachelor", "bs", "bsc", "undergrad", "undergraduate"]):
            undergrad_intent = True
            level = level or "BS"

        # JSON search by field/interest words
        json_hits = self.catalog.search(raw, limit=30)
        if level:
            # normalize common short forms
            lvl_norm = level.strip().lower()
            if lvl_norm in ("bs", "bsc", "bachelor", "undergrad", "undergraduate"):
                lvl_norm = "bachelor"
            json_hits = [h for h in json_hits if lvl_norm in str(h.get("level", "")).lower()]
        # semantic augment
        q = f"{raw} career opportunities field study {level}".strip()
        docs = self.retriever.invoke(q)
        seen = set([str(p.get("title", "")).lower() for p in json_hits])
        for d in docs:
            t = str(d.metadata.get("title", "")).strip()
            if t and t.lower() not in seen:
                meta_level = str(d.metadata.get("level", "")).lower()
                if level:
                    # only include if matches requested level
                    if level.strip().lower() not in meta_level and not (undergrad_intent and "bachelor" in meta_level):
                        continue
                json_hits.append({
                    "title": t,
                    "level": d.metadata.get("level", ""),
                    "field": d.metadata.get("field", ""),
                    "duration_years": d.metadata.get("duration_years", ""),
                })
                seen.add(t.lower())
        if not json_hits:
            return f"No specific recommendations found for '{raw}'. Try a broader term (e.g., technology, business, engineering)."
        # Rank and format results: prefer exact field matches and shorter duration
        # Simple ranking heuristic: exact field match first, then level match
        def score_prog(p):
            s = 0
            if raw_l and (raw_l in str(p.get("title", "")).lower() or raw_l in str(p.get("field", "")).lower()):
                s += 20
            if level and level.strip().lower() in str(p.get("level", "")).lower():
                s += 10
            try:
                s += 5 / (float(p.get("duration_years") or 4) )
            except Exception:
                s += 0
            return s

        json_hits_sorted = sorted(json_hits, key=score_prog, reverse=True)

        # Choose top 3 primary recommendations and next 3 runner-ups
        primaries = json_hits_sorted[:3]
        runners = json_hits_sorted[3:6]

        header = f"Top recommendations for '{raw}'{(' at level ' + level) if level else ''}:\n\n"
        lines = [header]
        if primaries:
            lines.append("Primary recommendations:")
            lines += [_format_program_line(p) for p in primaries]
        if runners:
            lines.append("\nRunner-up options:")
            lines += [_format_program_line(p) for p in runners]

        lines.append("\nIf you want, I can give more details on any of these programs (courses, admission criteria, career paths).")
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

    def _tool_ask_human(self, note: str) -> str:
        # Lightweight hook: surface a message that upstream UI can detect to prompt a human
        msg = (note or "").strip() or "Need human input to proceed (clarify preferences, constraints, or compare options)."
        return f"[HUMAN_NEEDED] {msg}"

    def _build_agent(self):
        tools: List[Tool] = [
            self._wrap(self._tool_by_field, name="degree_by_field", description="List degree programs in a field. Input: field name (e.g., 'Computer Science')."),
            self._wrap(self._tool_by_level, name="degree_by_level", description="List degree programs by level. Input: level (e.g., 'Bachelor', 'Master', 'PhD', 'BS', 'MS')."),
            self._wrap(self._tool_details, name="degree_details", description="Get details for a specific program. Input: program title."),
            self._wrap(self._tool_compare, name="degree_compare", description="Compare two programs. Input: 'Program A vs Program B' or 'Program A | Program B'."),
            self._wrap(self._tool_recommend, name="degree_recommend", description="Recommend programs for an interest area. Input: e.g., 'Artificial Intelligence; level=BS'."),
            self._wrap(self._tool_semantic, name="degree_search_semantic", description="Return relevant context via semantic search of the degree corpus. Input: full question."),
            self._wrap(self._tool_hybrid, name="degree_search_hybrid", description="Hybrid search combining catalog (JSON) matches and semantic excerpts. Input: full question."),
            self._wrap(self._tool_ask_human, name="ask_human", description="Request human input when preferences/constraints are ambiguous. Input: what to ask the human."),
        ]

        # Instruction prompt for the agent
        system_prompt = PromptTemplate(
            input_variables=["context", "question"],
            template=(
                f"{degree_advisor_prompt}\n\n"
                "Use tools liberally to retrieve facts. If uncertain, call 'ask_human' to solicit clarification instead of guessing.\n"
                "Prefer catalog (JSON) facts when available; verify or enrich with semantic search. Keep answers concise but comprehensive."
            ),
        ).template

        # expose the system prompt text so streaming calls can include it as a SystemMessage
        self.system_prompt_text = system_prompt

        return create_react_agent(
            model=llm,
            tools=tools,
            checkpointer=self.checkpointer,
            name="Degree Advisor",
        )

    def get_agent(self):
        return self.agent

    def stream(self, question: str):
        config = {"configurable": {"thread_id": "degree_react"}}
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
    # Quick manual test
    builder = DegreeReactAgentBuilder()
    prompt = "I'm interested in AI and data science at the BS level. What programs do you recommend?"
    print("=== Degree Advisor ReAct Agent Test ===\n")
    final = ""
    for msg in builder.stream(prompt):
        final = msg
    print(final)