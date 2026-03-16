from __future__ import annotations
import os
import json
import re
import sys
from difflib import get_close_matches
from pathlib import Path
from typing import Callable, List, Dict, Any, Optional

from langchain.agents import Tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.documents import Document
from langchain.prompts import PromptTemplate
from langchain_core.tools import tool

# Add the root directory to the Python path so we can import from root modules
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from config import llm, embeddings
from vector_store_manager import VectorStoreManager, VectorStoreType


# ----------------- Shared helpers -----------------
def _strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(text))
    return re.sub(r"\s+", " ", text).strip()


def _norm_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _normalize_name(name: str) -> str:
    s = _norm_whitespace(name).lower()
    s = re.sub(r"\b(dr|prof|mr|mrs|ms)\.?\s+", "", s)
    return re.sub(r"[^a-z\s]", "", s)


def _name_tokens(s: str) -> List[str]:
    s = _normalize_name(s)
    toks = [t for t in s.split() if t]
    return toks


def _load_faculty_jsons(data_dir: str) -> List[Dict[str, Any]]:
    people: List[Dict[str, Any]] = []
    if not os.path.isdir(data_dir):
        return people
    for fname in os.listdir(data_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(data_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                arr = json.load(f)
            if isinstance(arr, list):
                dept_code = os.path.splitext(fname)[0].upper()
                for obj in arr:
                    if isinstance(obj, dict):
                        obj.setdefault("Department", dept_code)
                        people.append(obj)
        except Exception:
            continue
    return people


def _faculty_display_name(p: Dict[str, Any]) -> str:
    title = _norm_whitespace(str(p.get("Title") or ""))
    name = _norm_whitespace(str(p.get("Name") or ""))
    if title and not name.lower().startswith(title.lower()):
        return f"{title} {name}".strip()
    return name or "Unknown"


def _person_to_document(p: Dict[str, Any]) -> Document:
    """Create a single markdown style document for retrieval."""
    name_disp = _faculty_display_name(p)
    dept = _norm_whitespace(str(p.get("Department") or p.get("Dept_ID") or ""))
    email = _norm_whitespace(str(p.get("Email") or ""))
    designation = _norm_whitespace(str(p.get("Designation_Title") or ""))
    summary = _strip_html(p.get("summary") or "")

    def _fmt_list(key: str) -> List[str]:
        items = p.get(key) or []
        out: List[str] = []
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    title = it.get("Title") or it.get("PublicationTitle") or it.get("Degree") or it.get("Position")
                    year = it.get("Year") or it.get("year")
                    venue = it.get("Journal") or it.get("Conference")
                    parts = [x for x in [title, year, venue] if x]
                    if parts:
                        out.append(_norm_whitespace(" - ".join(parts)))
                else:
                    out.append(_norm_whitespace(str(it)))
        return out

    edu = _fmt_list("listEEdu") or ["N/A"]
    exp = _fmt_list("listEExpr") or ["N/A"]
    pubs = _fmt_list("listPublication") or ["N/A"]

    content = [
        f"# {name_disp}",
        f"Department: {dept}",
        f"Designation: {designation}",
        f"Email: {email}",
        "",
        "## Summary", summary or "N/A", "",
        "## Education", *[f"- {x}" for x in edu], "",
        "## Experience", *[f"- {x}" for x in exp], "",
        "## Publications", *[f"- {x}" for x in pubs]
    ]
    doc = Document(
        page_content="\n".join(content),
        metadata={
            "source": f"faculty:{p.get('Emp_ID')}",
            "name": name_disp,
            "dept": dept,
            "email": email,
            "designation": designation,
        },
    )
    return doc


class FacultyAgent:
    """Simplified Faculty Agent with structured tools and semantic fallback."""

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.manager = VectorStoreManager(embeddings=embeddings)
        data_dir = self.manager.configs[VectorStoreType.FACULTY].data_source
        self.data_dir = data_dir
        self.people: List[Dict[str, Any]] = _load_faculty_jsons(data_dir)
        self.retriever = None

        # Build simple name/email indexes
        self.name_index: Dict[str, Dict[str, Any]] = {}
        self.email_index: Dict[str, Dict[str, Any]] = {}
        for person in self.people:
            norm = _normalize_name(person.get("Name") or _faculty_display_name(person))
            if norm:
                self.name_index[norm] = person
            em = _norm_whitespace(str(person.get("Email") or "")).lower()
            if em:
                self.email_index[em] = person

        # Faculty data is optional in local/dev setups. Missing sources should
        # not prevent the API from importing or starting.
        if os.path.isdir(data_dir):
            try:
                self.retriever = self.manager.get_retriever(
                    VectorStoreType.FACULTY, use_ensemble=True
                )
            except FileNotFoundError:
                self.retriever = None
        self.prompt = PromptTemplate(
            input_variables=["context", "question"],
            template=(
                "You answer questions about university faculty.\n"
                "If a direct tool result was provided, rely on it. If not enough info, use context.\n"
                "If answer truly not present, output ONLY: NOT_FOUND_IN_DOCUMENTS.\n\n"
                "Context:\n{context}\n\nQuestion: {question}\nAnswer:"
            ),
        )

    # ------------- Basic person resolution -------------
    def _resolve_person(self, raw_name: str) -> Optional[Dict[str, Any]]:
        if not raw_name:
            return None
        norm = _normalize_name(raw_name)
        if norm in self.name_index:
            return self.name_index[norm]
        # Bag-of-words overlap score across known names
        q_tokens = set(_name_tokens(norm))
        best_key = None
        best_score = 0.0
        if q_tokens:
            for key in self.name_index.keys():
                k_tokens = set(_name_tokens(key))
                if not k_tokens:
                    continue
                inter = len(q_tokens & k_tokens)
                if inter == 0:
                    continue
                # Jaccard-like with query emphasis
                score = inter / max(1, len(q_tokens)) + 0.25 * (inter / max(1, len(k_tokens)))
                if score > best_score:
                    best_score = score
                    best_key = key
        if best_key and best_score >= 0.6:
            return self.name_index.get(best_key)
        # Fuzzy fallback (looser cutoff if short query)
        cutoff = 0.75 if len(norm) <= 10 else 0.8
        matches = get_close_matches(norm, list(self.name_index.keys()), n=1, cutoff=cutoff)
        if matches:
            return self.name_index[matches[0]]
        return None

    def _semantic_answer(self, question: str, stream: bool = True) -> str:
        if self.retriever is None:
            return (
                "Faculty data is not available in this environment. "
                f"Expected source directory: {self.data_dir}"
            )
        try:
            docs = self.retriever.invoke(question)
            context = "\n".join([doc.page_content for doc in docs])
            prompt_text = self.prompt.format(context=context, question=question)
            if stream:
                try:
                    response = llm.stream([HumanMessage(content=prompt_text)])
                    full_response = ""
                    for chunk in response:
                        if hasattr(chunk, 'content') and chunk.content:
                            print(chunk.content, end="", flush=True)
                            full_response += chunk.content
                    print()  # newline
                    return full_response
                except Exception as e:
                    if self.debug:
                        print(f"Error generating response: {e}")
                    return "Error generating response"
            else:
                resp = llm.invoke([HumanMessage(content=prompt_text)])
                return resp.content if hasattr(resp, "content") else str(resp)
        except Exception as e:
            error_msg = f"Error in semantic search: {e}"
            if stream and self.debug:
                print(error_msg)
            return error_msg

    # ---------------- Structured lookups ----------------
    def _is_summary_like(self, q: str) -> bool:
        return bool(re.search(r"\b(summary|bio|about|profile)\b", q.lower()))

    def _format_list_field(self, items: Any) -> List[str]:
        lines: List[str] = []
        if not items:
            return lines
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    title = it.get("Title") or it.get("title") or it.get("PublicationTitle")
                    year = it.get("Year") or it.get("year")
                    venue = it.get("Journal") or it.get("Conference") or it.get("venue")
                    if title:
                        s = f"{title}"
                        if year:
                            s += f" ({year})"
                        if venue:
                            s += f", {venue}"
                        lines.append(_norm_whitespace(_strip_html(s)))
                    else:
                        s = ", ".join(f"{k}: {v}" for k, v in it.items() if v and isinstance(v, (str, int)))
                        lines.append(_norm_whitespace(_strip_html(s or json.dumps(it, ensure_ascii=False))))
                else:
                    lines.append(_norm_whitespace(_strip_html(str(it))))
        else:
            lines.append(_norm_whitespace(_strip_html(str(items))))
        return lines

    # ---------------- Tool functions (structured fetchers) ----------------
    def _tool_email(self, person: Dict[str, Any]) -> Optional[str]:
        email_val = _norm_whitespace(str(person.get("Email") or ""))
        return email_val or None

    def _tool_publications(self, person: Dict[str, Any]) -> Optional[str]:
        items = person.get("listPublication") or []
        lines = self._format_list_field(items)
        if not lines:
            return None
        header = f"All publications of {_faculty_display_name(person)}:"
        body = "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines))
        return f"{header}\n{body}"

    def _tool_publications_limited(self, person: Dict[str, Any], n: int) -> Optional[str]:
        items = person.get("listPublication") or []
        lines = self._format_list_field(items)
        if not lines:
            return None
        n = max(1, min(n, len(lines)))
        header = f"Top {n} publications of {_faculty_display_name(person)}:"
        body = "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines[:n]))
        return f"{header}\n{body}"

    def _tool_education(self, person: Dict[str, Any]) -> Optional[str]:
        lines = self._format_list_field(person.get("listEEdu") or [])
        if not lines:
            return None
        header = f"Education of {_faculty_display_name(person)}:"
        body = "\n".join(f"- {line}" for line in lines)
        return f"{header}\n{body}"

    def _tool_experience(self, person: Dict[str, Any]) -> Optional[str]:
        lines = self._format_list_field(person.get("listEExpr") or [])
        if not lines:
            return None
        header = f"Experience of {_faculty_display_name(person)}:"
        body = "\n".join(f"- {line}" for line in lines)
        return f"{header}\n{body}"

    def _tool_designation(self, person: Dict[str, Any]) -> Optional[str]:
        val = _norm_whitespace(str(person.get("Designation_Title") or ""))
        if not val:
            return None
        return f"Designation of {_faculty_display_name(person)}: {val}"

    def _tool_department(self, person: Dict[str, Any]) -> Optional[str]:
        val = _norm_whitespace(str(person.get("Department") or person.get("Dept_ID") or ""))
        if not val:
            return f"Department of {_faculty_display_name(person)}: N/A"
        return f"Department of {_faculty_display_name(person)}: {val}"

    def _tool_extension(self, person: Dict[str, Any]) -> Optional[str]:
        val = _norm_whitespace(str(person.get("Extension") or ""))
        if not val:
            return None
        return f"Extension of {_faculty_display_name(person)}: {val}"

    def _tool_website(self, person: Dict[str, Any]) -> Optional[str]:
        val = _norm_whitespace(str(person.get("Website") or ""))
        if not val:
            return None
        return f"Website of {_faculty_display_name(person)}: {val}"

    def _tool_hec_supervisor(self, person: Dict[str, Any]) -> Optional[str]:
        yn = "Yes" if bool(person.get("hec_supervisor")) else "No"
        return f"HEC Supervisor status of {_faculty_display_name(person)}: {yn}"

    def _person_markdown(self, person: Dict[str, Any]) -> str:
        name_disp = _faculty_display_name(person)
        summary = _strip_html(person.get("summary") or "")
        dept = _norm_whitespace(str(person.get("Department") or person.get("Dept_ID") or ""))
        email = _norm_whitespace(str(person.get("Email") or ""))
        designation = _norm_whitespace(str(person.get("Designation_Title") or ""))
        extension = _norm_whitespace(str(person.get("Extension") or ""))
        website = _norm_whitespace(str(person.get("Website") or ""))

        edu_lines = self._format_list_field(person.get("listEEdu") or [])
        exp_lines = self._format_list_field(person.get("listEExpr") or [])
        pub_lines = self._format_list_field(person.get("listPublication") or [])

        lines = [
            f"# {name_disp}",
            f"Department: {dept or 'N/A'}",
            f"Designation: {designation or 'N/A'}",
            f"Email: {email or 'N/A'}",
            f"Extension: {extension or 'N/A'}",
            f"Website: {website or 'N/A'}",
            "",
            "## Summary",
            summary or "N/A",
            "",
            "## Education",
            *([f"- {x}" for x in edu_lines] if edu_lines else ["- N/A"]),
            "",
            "## Experience",
            *([f"- {x}" for x in exp_lines] if exp_lines else ["- N/A"]),
            "",
            "## Publications",
            *([f"- {x}" for x in pub_lines] if pub_lines else ["- N/A"]),
        ]
        return "\n".join(lines)

    def _generate_person_summary(self, person: Dict[str, Any], question: str, stream: bool = True) -> str:
        context = self._person_markdown(person)
        prompt = PromptTemplate(
            input_variables=["context", "question"],
            template=(
                "You are an assistant that writes concise factual bios from structured faculty data.\n"
                "Use ONLY the provided context. Do not invent details.\n"
                "If some sections are missing, just omit them.\n\n"
                "Context (faculty profile):\n{context}\n\n"
                "Task: {question}\n"
                "Output: A short, well-structured paragraph or two summarizing the person and their background."
            ),
        )
        prompt_text = prompt.format(context=context, question=question)

        if stream:
            try:
                response = llm.stream([HumanMessage(content=prompt_text)])
                full_response = ""
                for chunk in response:
                    if hasattr(chunk, 'content') and chunk.content:
                        print(chunk.content, end="", flush=True)
                        full_response += chunk.content
                print("\n")
                return full_response
            except Exception as e:
                print(f"Error generating summary: {e}")
                return "Error generating summary"
        else:
            try:
                resp = llm.invoke([HumanMessage(content=prompt_text)])
                return getattr(resp, "content", str(resp))
            except Exception as e:
                return f"Error generating summary: {e}"

    def _render_full_profile(self, person: Dict[str, Any]) -> str:
        return self._person_markdown(person)

    def _compose_email(self, person_or_email: Any, purpose: str, stream: bool = False) -> str:
        """Compose a concise, professional email. Accepts either a person dict or an email string.

        Returns a formatted string with To, Subject, Body. Does not invent email addresses.
        """
        person = None
        email = None
        name_disp = None
        designation = None
        dept = None

        if isinstance(person_or_email, dict):
            person = person_or_email
        elif isinstance(person_or_email, str):
            s = person_or_email.strip()
            if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", s):
                email = s
            else:
                person = self._resolve_person(s)

        if person:
            name_disp = _faculty_display_name(person)
            designation = _norm_whitespace(str(person.get("Designation_Title") or "")) or None
            dept = _norm_whitespace(str(person.get("Department") or person.get("Dept_ID") or "")) or None
            email = email or _norm_whitespace(str(person.get("Email") or "")) or None

        if not email:
            # Without a concrete email, avoid composing to an unknown address
            return "NOT_FOUND_IN_DOCUMENTS"

        recip_str = name_disp or "Sir/Madam"
        role_hint = f", {designation}" if designation else ""
        dept_hint = f" ({dept})" if dept else ""

        sys_hint = "You write concise, professional emails."
        prompt = PromptTemplate(
            input_variables=["recipient", "role", "dept", "email", "purpose"],
            template=(
                "Draft a polite, concise email. Output exactly these sections in order:\n"
                "To: {email}\n"
                "Subject: A clear, specific subject line\n\n"
                "Body: 120-180 words, formal but warm.\n"
                "Constraints:\n"
                "- Address the recipient as {recipient}{role}{dept}.\n"
                "- State the purpose clearly upfront.\n"
                "- No fabricated facts or personal claims; keep placeholders where needed.\n"
                "- End with thanks and sender placeholders.\n\n"
                "Purpose: {purpose}"
            ),
        )
        text = prompt.format(recipient=recip_str, role=role_hint, dept=dept_hint, email=email, purpose=purpose)
        try:
            if stream:
                chunks = llm.stream([HumanMessage(content=f"{sys_hint}\n\n{text}")])
                out = ""
                for ch in chunks:
                    if hasattr(ch, "content") and ch.content:
                        out += ch.content
                return out
            else:
                resp = llm.invoke([HumanMessage(content=f"{sys_hint}\n\n{text}")])
                return getattr(resp, "content", str(resp))
        except Exception as e:
            return f"Error composing email: {e}"

    def _finalize_with_llm(self, question: str, context: str, stream: bool = False) -> str:
        """Compose the final natural-language answer using ONLY the provided context.

        The LLM must not invent facts not present in the context. Prefer concise, direct answers.
        If the question asks for N publications, include at most N items.
        """
        prompt = PromptTemplate(
            input_variables=["question", "context"],
            template=(
                "You are a precise university assistant. Answer ONLY using the given context.\n"
                "- Do not hallucinate or invent missing data.\n"
                "- If the user asks for a number of items (e.g., publications), include at most that many.\n"
                "- Prefer a short, clear answer over long lists.\n\n"
                "Question: {question}\n\n"
                "Context:\n{context}\n\n"
                "Final answer:"
            ),
        )
        text = prompt.format(question=question, context=context)
        if stream:
            try:
                chunks = llm.stream([HumanMessage(content=text)])
                out = ""
                for ch in chunks:
                    if hasattr(ch, "content") and ch.content:
                        out += ch.content
                return out
            except Exception as e:
                return f"Error finalizing answer: {e}"
        else:
            try:
                resp = llm.invoke([HumanMessage(content=text)])
                return getattr(resp, "content", str(resp))
            except Exception as e:
                return f"Error finalizing answer: {e}"

    def _stream_finalize_with_llm(self, question: str, context: str):
        """Yield tokens while composing the final answer strictly from context."""
        prompt = PromptTemplate(
            input_variables=["question", "context"],
            template=(
                "You are a precise university assistant. Answer ONLY using the given context.\n"
                "- Do not hallucinate or invent missing data.\n"
                "- If the user asks for a number of items (e.g., publications), include at most that many.\n"
                "- Prefer a short, clear answer over long lists.\n\n"
                "Question: {question}\n\n"
                "Context:\n{context}\n\n"
                "Final answer:"
            ),
        )
        text = prompt.format(question=question, context=context)
        try:
            chunks = llm.stream([HumanMessage(content=text)])
            for ch in chunks:
                if hasattr(ch, "content") and ch.content:
                    yield ch.content
        except Exception as e:
            yield f"Error finalizing answer: {e}"

    # ---------------- Public API ----------------
    def answer(self, question: str, stream: bool = True) -> str:
        if not self.people and self.retriever is None:
            return (
                "Faculty data is not available in this environment. "
                f"Expected source directory: {self.data_dir}"
            )
        latest_query = self._extract_latest_user_query(question) or question
        field = self._infer_field(latest_query)
        person = self._resolve_person_from_text(question)
        if person and field:
            try:
                tool_map = {
                    "email": self._tool_email,
                    "publications": self._tool_publications,
                    "education": self._tool_education,
                    "experience": self._tool_experience,
                    "designation": self._tool_designation,
                    "department": self._tool_department,
                    "extension": self._tool_extension,
                    "website": self._tool_website,
                    "hec_supervisor": self._tool_hec_supervisor,
                    "summary": lambda p: self._generate_person_summary(p, f"Provide a concise factual summary of {_faculty_display_name(p)}.", stream=False),
                    "full_profile": self._render_full_profile,
                }
                fn = tool_map.get(field)
                if fn:
                    direct = None
                    if field == "publications":
                        count = self._extract_publication_count(latest_query)
                        if count:
                            direct = self._tool_publications_limited(person, count)
                        else:
                            direct = fn(person)
                    else:
                        direct = fn(person)
                    if isinstance(direct, str) and direct.strip():
                        # Always finalize with LLM for natural language answer using only the direct context
                        final = self._finalize_with_llm(question, direct, stream=stream)
                        return final
            except Exception:
                pass

        # Fall back to semantic answer (which already uses LLM) and finalize
        result = self._semantic_answer(question, stream=False)
        if not isinstance(result, str) or not result.strip():
            return f"I'm your faculty information assistant. Question: {question}"
        return self._finalize_with_llm(question, result, stream=stream)

    # Public tool methods for LLM to call
    @tool("get_faculty_email")
    def get_email(self, person_name: str) -> Optional[str]:
        """Return the email address of the specified faculty member.

        Inputs:
        - person_name: Full or partial name of a faculty member.

        Returns:
        - Email string if found, otherwise None.
        """
        person = self._resolve_person(person_name)
        return self._tool_email(person) if person else None

    @tool("get_faculty_publications")
    def get_publications(self, person_name: str) -> Optional[str]:
        """Return a formatted list of publications for the specified faculty member.

        Inputs:
        - person_name: Full or partial name of a faculty member.

        Returns:
        - Markdown formatted string of publications or None if not found.
        """
        person = self._resolve_person(person_name)
        return self._tool_publications(person) if person else None

    @tool("get_faculty_education")
    def get_education(self, person_name: str) -> Optional[str]:
        """Return education history for the specified faculty member.

        Inputs:
        - person_name: Full or partial name of a faculty member.

        Returns:
        - Markdown formatted string of degrees or None if not found.
        """
        person = self._resolve_person(person_name)
        return self._tool_education(person) if person else None

    @tool("get_faculty_experience")
    def get_experience(self, person_name: str) -> Optional[str]:
        """Return professional experience for the specified faculty member.

        Inputs:
        - person_name: Full or partial name of a faculty member.

        Returns:
        - Markdown formatted string of roles/positions or None if not found.
        """
        person = self._resolve_person(person_name)
        return self._tool_experience(person) if person else None

    @tool("get_faculty_designation")
    def get_designation(self, person_name: str) -> Optional[str]:
        """Return the current designation/title for the specified faculty member.

        Inputs:
        - person_name: Full or partial name of a faculty member.

        Returns:
        - Designation/title string or None if not found.
        """
        person = self._resolve_person(person_name)
        return self._tool_designation(person) if person else None

    @tool("get_faculty_department")
    def get_department(self, person_name: str) -> Optional[str]:
        """Return the department name for the specified faculty member.

        Inputs:
        - person_name: Full or partial name of a faculty member.

        Returns:
        - Department string or None if not found.
        """
        person = self._resolve_person(person_name)
        return self._tool_department(person) if person else None

    @tool("get_faculty_extension")
    def get_extension(self, person_name: str) -> Optional[str]:
        """Return the phone extension for the specified faculty member.

        Inputs:
        - person_name: Full or partial name of a faculty member.

        Returns:
        - Extension string or None if not found.
        """
        person = self._resolve_person(person_name)
        return self._tool_extension(person) if person else None

    @tool("get_faculty_website")
    def get_website(self, person_name: str) -> Optional[str]:
        """Return the personal or profile website for the specified faculty member.

        Inputs:
        - person_name: Full or partial name of a faculty member.

        Returns:
        - Website URL string or None if not found.
        """
        person = self._resolve_person(person_name)
        return self._tool_website(person) if person else None

    @tool("get_faculty_hec_status")
    def get_hec_supervisor(self, person_name: str) -> Optional[str]:
        """Return whether the specified faculty member is an HEC approved supervisor.

        Inputs:
        - person_name: Full or partial name of a faculty member.

        Returns:
        - String indicating HEC supervisor status, or None if not found.
        """
        person = self._resolve_person(person_name)
        return self._tool_hec_supervisor(person) if person else None

    @tool("get_faculty_summary")
    def get_summary(self, person_name: str) -> Optional[str]:
        """Generate a concise factual summary from the structured profile of a faculty member.

        Inputs:
        - person_name: Full or partial name of a faculty member.

        Returns:
        - Short Markdown summary or None if the person is not found.
        """
        person = self._resolve_person(person_name)
        if not person:
            return None
        return self._generate_person_summary(person, f"Provide a concise factual summary of {person_name}.", stream=False)

    @tool("get_faculty_full_profile")
    def get_full_profile(self, person_name: str) -> Optional[str]:
        """Return the full structured profile in Markdown for the specified faculty member.

        Inputs:
        - person_name: Full or partial name of a faculty member.

        Returns:
        - Markdown string containing email, designation, department, education, experience, and publications; or None if not found.
        """
        person = self._resolve_person(person_name)
        return self._render_full_profile(person) if person else None

    def semantic_answer(self, question: str, stream: bool = True) -> str:
        result = self._semantic_answer(question, stream=stream)
        if not isinstance(result, str) or not result.strip():
            return f"I'm your faculty information assistant. Question: {question}"
        return result

    # --------- Inference helpers ---------
    def _infer_field(self, text: str) -> Optional[str]:
        q = (text or "").lower()
        if re.search(r"\b(email|e-?mail|contact)\b", q):
            return "email"
        if re.search(r"\b(publications?|papers?|articles?)\b", q):
            return "publications"
        if re.search(r"\b(education|degrees?|qualification|academics?)\b", q):
            return "education"
        if re.search(r"\b(experience|positions?|employment|work\s*history)\b", q):
            return "experience"
        if re.search(r"\b(designation|title|role|position)\b", q):
            return "designation"
        if re.search(r"\b(department|dept)\b", q):
            return "department"
        if re.search(r"\b(extension|phone|ext)\b", q):
            return "extension"
        if re.search(r"\b(website|home\s*page|homepage|page|site)\b", q):
            return "website"
        if re.search(r"\bhec\s*supervis(or|orship|ors|ion)\b", q):
            return "hec_supervisor"
        if self._is_summary_like(q):
            return "summary"
        if re.search(r"\b(full\s*profile|everything|complete\s*details)\b", q):
            return "full_profile"
        return None

    def _extract_latest_user_query(self, text: str) -> Optional[str]:
        if not text:
            return None
        last_q_start = None
        for m in re.finditer(r"(?i)question:\s*", text):
            last_q_start = m.end()
        if last_q_start is not None:
            return text[last_q_start:].strip()
        lines = [ln.rstrip() for ln in text.splitlines()]
        for ln in reversed(lines):
            m = re.match(r"\s*(you|user)\s*:\s*(.*)", ln, flags=re.IGNORECASE)
            if m:
                return (m.group(2) or "").strip()
        meta_prefixes = ("history:", "context:", "person:", "tools:", "route:", "assistant:", "system:")
        for ln in reversed(lines):
            if not ln.strip():
                continue
            if ln.strip().lower().startswith(meta_prefixes):
                continue
            return ln.strip()
        return text.strip()

    def _resolve_person_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        if email_match:
            p = self.email_index.get(email_match.group(0).lower())
            if p:
                return p
        # Heuristic: try extracting name-like tail after 'of' or 'for'
        tail = text
        m = re.search(r"\b(?:of|for)\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            tail = m.group(1)
        # Attempt direct resolve on tail then whole text
        for candidate in (tail, text):
            qnorm = _normalize_name(candidate)
            # Longest key contained in qnorm
            best_key = None
            for key in self.name_index.keys():
                if key and key in qnorm:
                    if best_key is None or len(key) > len(best_key):
                        best_key = key
            if best_key:
                return self.name_index.get(best_key)
            # Token-overlap scoring
            q_tokens = set(_name_tokens(qnorm))
            best_key = None
            best_score = 0.0
            if q_tokens:
                for key in self.name_index.keys():
                    k_tokens = set(_name_tokens(key))
                    if not k_tokens:
                        continue
                    inter = len(q_tokens & k_tokens)
                    if inter == 0:
                        continue
                    score = inter / max(1, len(q_tokens)) + 0.25 * (inter / max(1, len(k_tokens)))
                    if score > best_score:
                        best_score = score
                        best_key = key
            if best_key and best_score >= 0.6:
                return self.name_index.get(best_key)
            # Fuzzy match as last resort
            cutoff = 0.8 if len(qnorm) > 10 else 0.7
            matches = get_close_matches(qnorm, list(self.name_index.keys()), n=1, cutoff=cutoff)
            if matches:
                return self.name_index.get(matches[0])
        return None

    def _extract_count(self, text: str) -> Optional[int]:
        if not text:
            return None
        m = re.search(r"\b(\d{1,3})\b", text)
        if not m:
            return None
        try:
            val = int(m.group(1))
            return val if val > 0 else None
        except Exception:
            return None

    def _extract_publication_count(self, text: str) -> Optional[int]:
        if not text:
            return None
        q = text.lower()
        pat_strong = [
            r"\btop\s*(\d{1,3})\s*(publications?|papers?|articles?)\b",
            r"\blist(?:\s*down)?\s*(\d{1,3})\s*(publications?|papers?|articles?)\b",
            r"\b(show|give|provide|share|mention|name|cite|display)\s*(?:me\s*)?(\d{1,3})\s*(publications?|papers?|articles?)\b",
            r"\b(\d{1,3})\s*(publications?|papers?|articles?)\b",
        ]
        for ps in pat_strong:
            m = re.search(ps, q)
            if m:
                for g in m.groups():
                    if g and g.isdigit():
                        try:
                            val = int(g)
                            if val > 0:
                                return val
                        except Exception:
                            pass
        return self._extract_count(text)
    
    def _search_by_designation(self, designation: str) -> List[Dict[str, Any]]:
        """Search for faculty members by designation.
        
        Args:
            designation: The designation to search for (e.g., "Director", "Professor")
            
        Returns:
            List of faculty members with matching designation
        """
        if not designation:
            return []
        
        # Normalize the search term
        norm_designation = _norm_whitespace(designation).lower()
        
        # Find matching faculty
        matches = []
        for person in self.people:
            person_designation = _norm_whitespace(str(person.get("Designation_Title") or "")).lower()
            if norm_designation in person_designation or person_designation in norm_designation:
                matches.append(person)
        
        return matches

    def stream_answer(self, question: str):
        yield self.answer(question, stream=False)


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
      - search_faculty_by_designation (returns list of names)
      - faculty_search (semantic fallback over faculty corpus)

    Notes:
    - Tools accept a single string input. For summary/full profile, pass the person name.
    - "faculty_search" accepts a full question string and returns an answer via semantic retrieval.
    """

    def __init__(self):
        self.fac = FacultyAgent(debug=False)
        # Removed MemorySaver - conversation context now passed via messages from wrapper
        self.system_prompt_text = (
            "You are a precise university faculty assistant for FAST-NU (Islamabad).\n"
            "Tool selection policy:\n"
            "- When the user asks WHO holds a role/title (e.g., 'Who is the rector', 'vice chancellor', 'director of X', 'HOD of Y'), first use 'search_faculty_by_designation' with the role text to get candidates.\n"
            "- When the user asks for a specific attribute of a person (email, education, experience, designation, department, website, extension, HEC supervisor), call the corresponding get_faculty_* tool with the person's name, then call finalize_answer with 'question\\n\\n---\\n\\ncontext'.\n"
            "- If a structured tool returns NOT_FOUND_IN_DOCUMENTS, you may use 'faculty_search' as a fallback.\n"
            "- Always produce the final response via 'finalize_answer' using ONLY tool-derived context.\n"
        )
        self.agent = self._build_agent()

    def _wrap(self, fn: Callable[[str], str], name: str, description: str) -> Tool:
        return Tool(name=name, func=fn, description=description)

    def _build_agent(self):
        fac = self.fac

        # Structured tools with explicit parameter names using @tool
        @tool("get_faculty_email")
        def get_faculty_email(person_name: str) -> str:
            """Return the email address of the specified faculty member. Input: person_name (string)."""
            p = fac._resolve_person(person_name)
            return fac._tool_email(p) if p else "NOT_FOUND_IN_DOCUMENTS"

        @tool("get_faculty_publications")
        def get_faculty_publications(person_name: str) -> str:
            """Return a numbered list of publications for the faculty member. Input: person_name (string).

            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            If the user requested a specific count, prefer the get_faculty_publications_with_count tool instead.
            """
            p = fac._resolve_person(person_name)
            if not p:
                return "NOT_FOUND_IN_DOCUMENTS"
            # We return full list, but also support an inline pattern in the name like 'Name|N'.
            if "|" in person_name:
                base, _, tail = person_name.partition("|")
                try:
                    n = int(tail.strip())
                    p2 = fac._resolve_person(base.strip())
                    return fac._tool_publications_limited(p2, n) if p2 else "NOT_FOUND_IN_DOCUMENTS"
                except Exception:
                    pass
            return fac._tool_publications(p)

        @tool("get_faculty_publications_with_count")
        def get_faculty_publications_with_count(person_name: str, count: int) -> str:
            """Return only 'count' publications for the faculty member. Inputs: person_name (string), count (int).

            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            """
            p = fac._resolve_person(person_name)
            if not p:
                return "NOT_FOUND_IN_DOCUMENTS"
            if count is None or count <= 0:
                return fac._tool_publications(p)
            return fac._tool_publications_limited(p, int(count))

        @tool("get_faculty_education")
        def get_faculty_education(person_name: str) -> str:
            """Return the education history as bullet points. Input: person_name (string).

            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            """
            p = fac._resolve_person(person_name)
            return fac._tool_education(p) if p else "NOT_FOUND_IN_DOCUMENTS"

        @tool("get_faculty_experience")
        def get_faculty_experience(person_name: str) -> str:
            """Return the work experience as bullet points. Input: person_name (string).

            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            """
            p = fac._resolve_person(person_name)
            return fac._tool_experience(p) if p else "NOT_FOUND_IN_DOCUMENTS"

        @tool("get_faculty_designation")
        def get_faculty_designation(person_name: str) -> str:
            """Return the current designation/title. Input: person_name (string).

            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            """
            p = fac._resolve_person(person_name)
            return fac._tool_designation(p) if p else "NOT_FOUND_IN_DOCUMENTS"

        @tool("get_faculty_department")
        def get_faculty_department(person_name: str) -> str:
            """Return the department. Input: person_name (string).

            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            """
            p = fac._resolve_person(person_name)
            return fac._tool_department(p) if p else "NOT_FOUND_IN_DOCUMENTS"

        @tool("get_faculty_extension")
        def get_faculty_extension(person_name: str) -> str:
            """Return the phone extension, if available. Input: person_name (string).

            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            """
            p = fac._resolve_person(person_name)
            return fac._tool_extension(p) if p else "NOT_FOUND_IN_DOCUMENTS"

        @tool("get_faculty_website")
        def get_faculty_website(person_name: str) -> str:
            """Return the personal or official website URL, if available. Input: person_name (string).

            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            """
            p = fac._resolve_person(person_name)
            return fac._tool_website(p) if p else "NOT_FOUND_IN_DOCUMENTS"

        @tool("get_faculty_hec_status")
        def get_faculty_hec_status(person_name: str) -> str:
            """Return whether the person is an HEC-recognized PhD supervisor (Yes/No). Input: person_name (string).

            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            """
            p = fac._resolve_person(person_name)
            return fac._tool_hec_supervisor(p) if p else "NOT_FOUND_IN_DOCUMENTS"

        @tool("get_faculty_summary")
        def get_faculty_summary(person_name: str) -> str:
            """Return a concise generated summary paragraph for the person. Input: person_name (string).

            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            """
            p = fac._resolve_person(person_name)
            return fac._generate_person_summary(p, f"Provide a concise factual summary of {person_name}.", stream=False) if p else "NOT_FOUND_IN_DOCUMENTS"

        @tool("search_faculty_by_designation")
        def search_faculty_by_designation(designation: str) -> str:
            """Search for faculty by designation/title (e.g., 'Rector', 'Vice Chancellor', 'Director', 'HOD').

            Input: designation (string). Examples: 'rector', 'vice chancellor', 'director admissions', 'hod cs'.
            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            """
            matches = fac._search_by_designation(designation)
            if not matches:
                return f"No faculty found with designation: {designation}"

            # Normalize search token for exact-match preference
            norm_designation = _norm_whitespace(designation).lower()

            exact_matches = []
            partial_matches = []
            for person in matches:
                person_designation = _norm_whitespace(str(person.get("Designation_Title") or "")).lower()
                # Word-boundary exact match preference
                if re.search(rf"\b{re.escape(norm_designation)}\b", person_designation):
                    exact_matches.append(person)
                else:
                    partial_matches.append(person)

            ordered = exact_matches + partial_matches

            result_lines = [f"Faculty with designation '{designation}':\n"]

            if exact_matches:
                # Mark the primary candidate to encourage the agent to use it
                primary = exact_matches[0]
                pname = _faculty_display_name(primary)
                pdept = _norm_whitespace(str(primary.get("Department") or primary.get("Dept_ID") or ""))
                pemail = _norm_whitespace(str(primary.get("Email") or ""))
                result_lines.append("PRIMARY MATCH:\n")
                result_lines.append(f"- {pname}\n")
                if pdept:
                    result_lines.append(f"  Department: {pdept}\n")
                if pemail:
                    result_lines.append(f"  Email: {pemail}\n")
                result_lines.append("\n")

            # Then list remaining candidates with designation text for clarity
            result_lines.append("All matching candidates:\n\n")
            for i, person in enumerate(ordered, 1):
                name = _faculty_display_name(person)
                dept = _norm_whitespace(str(person.get("Department") or person.get("Dept_ID") or ""))
                email = _norm_whitespace(str(person.get("Email") or ""))
                designation_text = _norm_whitespace(str(person.get("Designation_Title") or "N/A"))
                result_lines.append(f"{i}. {name}\n")
                result_lines.append(f"   Designation: {designation_text}\n")
                if dept:
                    result_lines.append(f"   Department: {dept}\n")
                if email:
                    result_lines.append(f"   Email: {email}\n")
                result_lines.append("\n")

            return "".join(result_lines)

        @tool("get_faculty_full_profile")
        def get_faculty_full_profile(person_name: str) -> str:
            """Return full profile (markdown) including education, experience, publications. Input: person_name (string).

            After using this tool, always call finalize_answer with 'question\n\n---\n\ncontext' to produce the final reply.
            """
            p = fac._resolve_person(person_name)
            return fac._render_full_profile(p) if p else "NOT_FOUND_IN_DOCUMENTS"

        @tool("faculty_search")
        def faculty_search(question: str) -> str:
            """Answer a faculty-related question via semantic retrieval over the faculty corpus. Input: question (string)."""
            return fac.semantic_answer(question, stream=False)

        @tool("simple_compose_email")
        def simple_compose_email(recipient: str, purpose: str) -> str:
            """Compose a professional email to a given recipient (name or email) for a stated purpose.

            Inputs:
            - recipient: A faculty member's name or a direct email address.
            - purpose: One-line description of the email's purpose (e.g., 'Request FYP supervision').

            Returns:
            - A formatted email with To, Subject, Body; or NOT_FOUND_IN_DOCUMENTS if no valid email is available.
            """
            # Resolve recipient first if it's a name; otherwise use email directly
            if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", recipient or ""):
                return fac._compose_email(recipient, purpose, stream=False)
            person = fac._resolve_person(recipient)
            if not person:
                return "NOT_FOUND_IN_DOCUMENTS"
            return fac._compose_email(person, purpose, stream=False)

        @tool("finalize_answer")
        def finalize_answer(input_text: str) -> str:
            """Format the final natural-language answer from context. Input: 'question\n\n---\n\ncontext'.

            The model must answer only from the context segment. Use concise wording and obey any counts in the question.
            """
            # Split on separator to extract question and context
            parts = input_text.split("\n\n---\n\n", 1)
            if len(parts) != 2:
                return input_text
            q, ctx = parts
            return fac._finalize_with_llm(q, ctx, stream=False)

        tools: List[Tool] = [
            get_faculty_email,
            get_faculty_publications_with_count,
            get_faculty_publications,
            get_faculty_education,
            get_faculty_experience,
            get_faculty_designation,
            get_faculty_department,
            get_faculty_extension,
            get_faculty_website,
            get_faculty_hec_status,
            get_faculty_summary,
            get_faculty_full_profile,
            faculty_search,
            simple_compose_email,
            finalize_answer,
            search_faculty_by_designation
        ]

        return create_react_agent(
            model=llm,
            tools=tools,
            # No checkpointer - stateless agent receives context via messages
            name="faculty_agent",
        )

    def get_agent(self):
        return self.agent

    def stream(self, question: str, session_id: str = "default"):
        """Stream the final, LLM-composed answer. Internally, run the tool-using agent, then finalize.

        This ensures the final text is always produced by the LLM using only tool-derived context, and
        respects requested counts (e.g., publications).
        """
        config = {"configurable": {"thread_id": f"faculty_react::{session_id}"}}
        last_content = ""
        for step in self.agent.stream(
            {"messages": [
                HumanMessage(content=question) if not getattr(self, "system_prompt_text", "") else None,
            ] if not getattr(self, "system_prompt_text", "") else [
                # Prepend a system hint to bias tool selection for roles like 'rector'
                # Note: create_react_agent accepts a list of messages; SystemMessage influences the model behavior.
                SystemMessage(content=self.system_prompt_text),
                HumanMessage(content=question),
            ]},
            config,
            stream_mode="values",
        ):
            if step.get("messages"):
                last_msg = step["messages"][-1]
                if hasattr(last_msg, "content") and isinstance(last_msg.content, str):
                    last_content = last_msg.content
        # After agent completes, stream the finalization
        for token in self.fac._stream_finalize_with_llm(question, last_content):
            yield token


# Helper to expose a compiled graph-like object for image export
def build_faculty_react_graph():
    return FacultyReactAgentBuilder().get_agent()


# Export name kept for compatibility without eager graph construction.
faculty_react_graph = None
