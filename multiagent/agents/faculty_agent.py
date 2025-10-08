import os
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from difflib import get_close_matches

# Add the root directory to the Python path so we can import from root modules
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langchain_core.documents import Document
from langchain.prompts import PromptTemplate
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from config import embeddings, llm
from vector_store_manager import VectorStoreManager, VectorStoreType


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
    """Simplified Faculty Agent.

    Responsibilities:
      1. Provide lightweight structured tool functions (email, publications, etc.).
      2. Provide semantic fallback via vector store retrieval.
      3. Avoid complex rule-based parsing; let the higher-level LLM decide when to call tools.
    """

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.manager = VectorStoreManager(embeddings=embeddings)
        data_dir = os.path.join("data", "faculty")
        self.people: List[Dict[str, Any]] = _load_faculty_jsons(data_dir)
        # Build simple name index
        self.name_index: Dict[str, Dict[str, Any]] = {}
        self.email_index: Dict[str, Dict[str, Any]] = {}
        for person in self.people:
            norm = _normalize_name(person.get("Name") or _faculty_display_name(person))
            if norm:
                self.name_index[norm] = person
            em = _norm_whitespace(str(person.get("Email") or "")).lower()
            if em:
                self.email_index[em] = person
        # Retriever (vector DB) for semantic fallback
        self.retriever = self.manager.get_retriever(VectorStoreType.FACULTY, use_ensemble=True)
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
        # Fuzzy fallback
        matches = get_close_matches(norm, list(self.name_index.keys()), n=1, cutoff=0.8)
        if matches:
            return self.name_index[matches[0]]
        return None

    def _semantic_answer(self, question: str, stream: bool = True) -> str:
        try:
            # Retrieve relevant documents
            docs = self.retriever.invoke(question)
            context = "\n".join([doc.page_content for doc in docs])
            
            # Format prompt
            prompt_text = self.prompt.format(context=context, question=question)
            
            if stream:
                try:
                    response = llm.stream([HumanMessage(content=prompt_text)])
                    full_response = ""
                    for chunk in response:
                        if hasattr(chunk, 'content') and chunk.content:
                            print(chunk.content, end="", flush=True)
                            full_response += chunk.content
                    print()  # Add newline after streaming
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
    # Legacy helper names kept minimal for compatibility
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

    # Removed: old direct keyword-based answering. This is now delegated to LLM + tools.

    def _person_markdown(self, person: Dict[str, Any]) -> str:
        """Render a single person's data to markdown (same schema as index docs)."""
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
        """Use LLM to synthesize a concise summary using all available fields, even if summary is empty."""
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

    # ---------------- Public API ----------------
    def answer(self, question: str, stream: bool = True) -> str:
        """Primary entry point used by the rest of the system.

        Strategy:
          1. Try to infer a specific field and person from the text (including any prior context included in the question). If found, use the corresponding tool for a precise answer.
          2. Otherwise, perform semantic retrieval over the faculty corpus.
          3. Keep deterministic fallback phrase if nothing retrieved.
        Tool calls should be orchestrated by a higher-level agent (future work) using the public get_* methods.
        """
        # 1) Heuristic tool invocation (person + field inference)
        # NOTE: The supervisor may prepend conversation history and hints (e.g., Person: email).
        # To avoid false matches (like picking 'email' from prior turns), infer the field
        # from the most recent user utterance only, while still using the full text to
        # resolve the person.
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
                    # Respect requested count for publications if specified
                    direct = None
                    if field == "publications":
                        # Extract desired count from the latest user query only,
                        # so numbers from prior context (e.g., "50 papers") don't leak in.
                        count = self._extract_publication_count(latest_query)
                        if count:
                            direct = self._tool_publications_limited(person, count)
                        else:
                            direct = fn(person)
                    else:
                        direct = fn(person)
                    if isinstance(direct, str) and direct.strip():
                        if stream:
                            print(direct)
                        return direct
            except Exception:
                # Fall through to semantic if tool lookup fails
                pass

        # 2) Semantic retrieval
        result = self._semantic_answer(question, stream=stream)
        if not isinstance(result, str) or not result.strip():
            return f"I'm your faculty information assistant. Question: {question}"
        return result

    # Public tool methods for LLM to call
    @tool("get_faculty_email")
    def get_email(self, person_name: str) -> Optional[str]:
        """Return the email address of the specified faculty member (person_name)."""
        person = self._resolve_person(person_name)
        return self._tool_email(person) if person else None

    @tool("get_faculty_publications")
    def get_publications(self, person_name: str) -> Optional[str]:
        """Return a numbered list of publications for the faculty member."""
        person = self._resolve_person(person_name)
        return self._tool_publications(person) if person else None

    @tool("get_faculty_education")
    def get_education(self, person_name: str) -> Optional[str]:
        """Return the education history of the specified faculty member as bullet points."""
        person = self._resolve_person(person_name)
        return self._tool_education(person) if person else None

    @tool("get_faculty_experience")
    def get_experience(self, person_name: str) -> Optional[str]:
        """Return the work experience of the specified faculty member as bullet points."""
        person = self._resolve_person(person_name)
        return self._tool_experience(person) if person else None

    @tool("get_faculty_designation")
    def get_designation(self, person_name: str) -> Optional[str]:
        """Return the current designation/title of the specified faculty member."""
        person = self._resolve_person(person_name)
        return self._tool_designation(person) if person else None

    @tool("get_faculty_department")
    def get_department(self, person_name: str) -> Optional[str]:
        """Return the department of the specified faculty member."""
        person = self._resolve_person(person_name)
        return self._tool_department(person) if person else None

    @tool("get_faculty_extension")
    def get_extension(self, person_name: str) -> Optional[str]:
        """Return the phone extension of the specified faculty member, if available."""
        person = self._resolve_person(person_name)
        return self._tool_extension(person) if person else None

    @tool("get_faculty_website")
    def get_website(self, person_name: str) -> Optional[str]:
        """Return the personal or official website URL of the specified faculty member, if available."""
        person = self._resolve_person(person_name)
        return self._tool_website(person) if person else None

    @tool("get_faculty_hec_status")
    def get_hec_supervisor(self, person_name: str) -> Optional[str]:
        """Return whether the specified faculty member is an HEC-recognized PhD supervisor (Yes/No)."""
        person = self._resolve_person(person_name)
        return self._tool_hec_supervisor(person) if person else None

    @tool("get_faculty_summary")
    def get_summary(self, person_name: str) -> Optional[str]:
        """Return a concise generated summary paragraph for the faculty member."""
        person = self._resolve_person(person_name)
        if not person:
            return None
        return self._generate_person_summary(person, f"Provide a concise factual summary of {person_name}.", stream=False)

    @tool("get_faculty_full_profile")
    def get_full_profile(self, person_name: str) -> Optional[str]:
        """Return a full profile (markdown) of the specified faculty member, including education, experience, and publications."""
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
        """Extract what looks like the latest user question from a history-enriched prompt.

        Heuristics (best-effort, non-destructive):
        - If there's a 'Question:' marker, take everything after the LAST occurrence.
        - Else, if there are lines prefixed with 'You:' or 'User:', take the last such line (after the colon).
        - Else, take the last non-empty line that doesn't look like metadata (History/Context/Person/etc.).
        """
        if not text:
            return None

        # 1) Prefer the last explicit Question: marker
        last_q_start = None
        for m in re.finditer(r"(?i)question:\s*", text):
            last_q_start = m.end()
        if last_q_start is not None:
            return text[last_q_start:].strip()

        # 2) Look for last 'You:' or 'User:' style prompt line
        lines = [ln.rstrip() for ln in text.splitlines()]
        for ln in reversed(lines):
            m = re.match(r"\s*(you|user)\s*:\s*(.*)", ln, flags=re.IGNORECASE)
            if m:
                return (m.group(2) or "").strip()

        # 3) Fallback to last non-metadata line
        meta_prefixes = ("history:", "context:", "person:", "tools:", "route:", "assistant:", "system:")
        for ln in reversed(lines):
            if not ln.strip():
                continue
            if ln.strip().lower().startswith(meta_prefixes):
                continue
            return ln.strip()

        # 4) Nothing sensible found
        return text.strip()

    def _resolve_person_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        # 1) Try email match from any previous context text
        email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        if email_match:
            p = self.email_index.get(email_match.group(0).lower())
            if p:
                return p
        # 2) Try name substring match against normalized keys
        qnorm = _normalize_name(text)
        best_key = None
        for key in self.name_index.keys():
            if key and key in qnorm:
                if best_key is None or len(key) > len(best_key):
                    best_key = key
        if best_key:
            return self.name_index.get(best_key)
        # 3) Fuzzy name similarity
        matches = get_close_matches(qnorm, list(self.name_index.keys()), n=1, cutoff=0.9)
        if matches:
            return self.name_index.get(matches[0])
        return None

    def _extract_count(self, text: str) -> Optional[int]:
        """Extract a small positive integer (like '5') from the query, if present."""
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
        """Prefer extracting a count that clearly refers to publications/papers.

        Strategy:
        1) Look for patterns like: 'top 5 publications', 'list 3 papers', '5 publications', '5 papers'.
        2) If not found, fallback to the first small integer in the text.
        """
        if not text:
            return None

        q = text.lower()
        # Strong patterns: number near publication keywords
        pat_strong = [
            r"\btop\s*(\d{1,3})\s*(publications?|papers?|articles?)\b",
            r"\blist(?:\s*down)?\s*(\d{1,3})\s*(publications?|papers?|articles?)\b",
            r"\b(show|give|provide|share|mention|name|cite|display)\s*(?:me\s*)?(\d{1,3})\s*(publications?|papers?|articles?)\b",
            r"\b(\d{1,3})\s*(publications?|papers?|articles?)\b",
        ]
        for ps in pat_strong:
            m = re.search(ps, q)
            if m:
                # Find first capturing group that is a number
                for g in m.groups():
                    if g and g.isdigit():
                        try:
                            val = int(g)
                            if val > 0:
                                return val
                        except Exception:
                            pass

        # Fallback: any small integer
        return self._extract_count(text)

    def stream_answer(self, question: str):
        """Stream the answer in chunks."""
        # For now, since faculty answers are often structured and fast, yield the full answer
        # But to make it stream, we can yield parts if needed
        # For semantic answers, use streaming LLM
        # But for simplicity, yield the full answer as one chunk
        yield self.answer(question, stream=False)


def main():
    import argparse
    import json as _json
    import textwrap

    def hr(char="-", n=60):
        print(char * n)

    def section(title: str):
        hr("=")
        print(title)
        hr("=")

    def subsection(title: str):
        hr("-")
        print(title)
        hr("-")

    def pretty(obj):
        try:
            print(_json.dumps(obj, indent=2, ensure_ascii=False))
        except Exception:
            print(str(obj))

    parser = argparse.ArgumentParser(description="Faculty Agent Debug CLI")
    parser.add_argument("--question", "-q", type=str, help="Ask a question once and exit")
    parser.add_argument("--debug", action="store_true", help="Enable agent debug logging")
    parser.add_argument("--debug-flow", action="store_true", help="Show planner, tool calls, and retrieval context")
    args = parser.parse_args()

    agent = FacultyAgent(debug=args.debug)

    # Lightweight tool registry using agent internals for reliable invocation
    tool_registry = {
        "get_faculty_email": {
            "desc": "Return the email address of the specified faculty member (person_name).",
            "call": lambda person_name: agent._tool_email(agent._resolve_person(person_name))
        },
        "get_faculty_publications": {
            "desc": "Return a numbered list of publications for the faculty member.",
            "call": lambda person_name: agent._tool_publications(agent._resolve_person(person_name))
        },
        "get_faculty_education": {
            "desc": "Return the education history of the specified faculty member as bullet points.",
            "call": lambda person_name: agent._tool_education(agent._resolve_person(person_name))
        },
        "get_faculty_experience": {
            "desc": "Return the work experience of the specified faculty member as bullet points.",
            "call": lambda person_name: agent._tool_experience(agent._resolve_person(person_name))
        },
        "get_faculty_designation": {
            "desc": "Return the current designation/title of the specified faculty member.",
            "call": lambda person_name: agent._tool_designation(agent._resolve_person(person_name))
        },
        "get_faculty_department": {
            "desc": "Return the department of the specified faculty member.",
            "call": lambda person_name: agent._tool_department(agent._resolve_person(person_name))
        },
        "get_faculty_extension": {
            "desc": "Return the phone extension of the specified faculty member, if available.",
            "call": lambda person_name: agent._tool_extension(agent._resolve_person(person_name))
        },
        "get_faculty_website": {
            "desc": "Return the personal or official website URL of the specified faculty member, if available.",
            "call": lambda person_name: agent._tool_website(agent._resolve_person(person_name))
        },
        "get_faculty_hec_status": {
            "desc": "Return whether the specified faculty member is an HEC-recognized PhD supervisor (Yes/No).",
            "call": lambda person_name: agent._tool_hec_supervisor(agent._resolve_person(person_name))
        },
        "get_faculty_full_profile": {
            "desc": "Return a full profile (markdown) of the specified faculty member, including education, experience, and publications.",
            "call": lambda person_name: agent._render_full_profile(agent._resolve_person(person_name))
        },
        "get_faculty_summary": {
            "desc": "Return a concise generated summary paragraph for the faculty member.",
            "call": lambda person_name: agent._generate_person_summary(agent._resolve_person(person_name), f"Provide a concise factual summary of {person_name}.", stream=False) if agent._resolve_person(person_name) else None
        },
    }

    def plan_tools(question: str) -> dict:
        """Ask the LLM to propose tool calls. Returns a dict with optional tool_calls list."""
        tools_desc = "\n".join([f"- {name}(person_name): {spec['desc']}" for name, spec in tool_registry.items()])
        planning_prompt = (
            "You are a planning assistant for answering faculty questions using tools.\n"
            "Given the user question, decide zero or more tool calls to fetch precise fields, then provide a final answer.\n"
            "Tools available:\n"
            f"{tools_desc}\n\n"
            "Rules:\n"
            "- Only call tools when necessary (e.g., for email, department, publications).\n"
            "- Use at most 3 tool calls.\n"
            "- If the person_name is not clearly specified, infer from the question if possible.\n"
            "- Respond ONLY with minified JSON matching this schema:\n"
            "  {\"tool_calls\": [{\"tool\": \"<tool_name>\", \"args\": {\"person_name\": \"<name>\"}}]}\n"
            "  If no tools are needed, respond with {\"tool_calls\": []}.\n\n"
            f"Question: {question}\n"
            "JSON:"
        )
        resp = llm.invoke([HumanMessage(content=planning_prompt)])
        content = getattr(resp, "content", str(resp))
        try:
            # Try direct parse
            return _json.loads(content)
        except Exception:
            # Try to extract JSON object heuristically
            import re as _re
            m = _re.search(r"\{[\s\S]*\}", content)
            if m:
                try:
                    return _json.loads(m.group(0))
                except Exception:
                    return {"tool_calls": []}
            return {"tool_calls": []}

    def execute_tools(tool_plan: dict) -> List[Dict[str, Any]]:
        """Execute planned tool calls and return a list of {tool, args, output}."""
        calls = tool_plan.get("tool_calls", []) or []
        results = []
        for i, call in enumerate(calls, 1):
            tool_name = call.get("tool")
            args = call.get("args") or {}
            person_name = args.get("person_name")
            fn = tool_registry.get(tool_name, {}).get("call")
            subsection(f"Tool {i}: {tool_name}({person_name!r})")
            if not fn:
                print("Unknown tool; skipping.")
                results.append({"tool": tool_name, "args": args, "output": None, "error": "unknown_tool"})
                continue
            try:
                out = fn(person_name)
                preview = (out or "").splitlines()
                preview = "\n".join(preview[:10])  # limit preview
                print(preview if preview else "<no output>")
                results.append({"tool": tool_name, "args": args, "output": out})
            except Exception as e:
                print(f"Error: {e}")
                results.append({"tool": tool_name, "args": args, "output": None, "error": str(e)})
        return results

    def retrieve_context(question: str, k_preview: int = 3) -> Dict[str, Any]:
        """Peek at retriever context for debugging and return assembled context text."""
        docs = agent.retriever.invoke(question)
        subsection("Top retrieval results")
        for i, d in enumerate(docs[:k_preview], 1):
            meta = d.metadata or {}
            title = meta.get("name") or meta.get("source") or "<doc>"
            print(f"{i}. {title} | source={meta.get('source', 'N/A')}")
        context_text = "\n".join(d.page_content for d in docs)
        return {"docs": docs, "context_text": context_text}

    def finalize_answer(question: str, tool_outputs: List[Dict[str, Any]], context_text: str) -> str:
        """Ask LLM to produce final answer using tool outputs and retrieval context."""
        tool_blobs = []
        for r in tool_outputs:
            if r.get("output"):
                tool_blobs.append(f"Tool {r['tool']} ->\n{r['output']}")
        tool_text = "\n\n".join(tool_blobs) if tool_blobs else "<no tools used>"
        final_prompt = PromptTemplate(
            input_variables=["question", "tools", "context"],
            template=(
                "You are answering a user question about university faculty.\n"
                "Use TOOL OUTPUTS first when present; otherwise, use CONTEXT.\n"
                "If the answer is not present, reply EXACTLY with: NOT_FOUND_IN_DOCUMENTS\n\n"
                "QUESTION:\n{question}\n\n"
                "TOOL OUTPUTS:\n{tools}\n\n"
                "CONTEXT:\n{context}\n\n"
                "Answer:"
            ),
        ).format(question=question, tools=tool_text, context=context_text)
        resp = llm.invoke([HumanMessage(content=final_prompt)])
        return getattr(resp, "content", str(resp))

    def handle_question(q: str):
        if not args.debug_flow:
            # Simple streaming answer
            subsection("Answer")
            agent.answer(q, stream=True)
            return
        # Full debug flow
        section("Planning")
        plan = plan_tools(q)
        pretty(plan)
        section("Tool execution")
        tool_results = execute_tools(plan)
        section("Retrieval")
        ret = retrieve_context(q)
        section("Final Answer")
        answer = finalize_answer(q, tool_results, ret.get("context_text", ""))
        print(answer)

    if args.question:
        handle_question(args.question)
        return

    print("\nFaculty Agent Debug CLI. Commands: 'tools' to list, 'exit' to quit.\n")
    while True:
        try:
            q = input("You: ").strip()
            if not q:
                continue
            if q.lower() in {"exit", "quit", "q"}:
                print("Goodbye!")
                break
            if q.lower() in {"tools", "help tools", "?tools"}:
                section("Available tools")
                for name, spec in tool_registry.items():
                    print(f"- {name}: {spec['desc']}")
                continue
            handle_question(q)
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()
