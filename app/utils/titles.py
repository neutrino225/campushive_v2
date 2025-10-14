"""Chat title generation utilities."""
from __future__ import annotations

import re
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage

from config import small_llm

_TITLE_SYSTEM_PROMPT = (
    "You generate short, human-friendly chat titles."
    " Return a single concise title (max 8 words) that captures the user's request."
    " Avoid quotation marks and punctuation beyond basic letters/numbers."
)


def _fallback_title(user_text: Optional[str], agent_text: Optional[str]) -> Optional[str]:
    """Fallback heuristic mirroring legacy behaviour."""
    if not user_text and not agent_text:
        return None

    source = (user_text or agent_text or "").strip()
    if not source:
        return None

    source = " ".join(source.split())
    lowered = source.lower()
    for prefix in (
        "please",
        "can you",
        "could you",
        "i want",
        "i need",
        "how do i",
        "how to",
        "what is",
        "tell me",
        "help me",
    ):
        if lowered.startswith(prefix + " "):
            source = source[len(prefix) + 1 :]
            break

    cut_idx = min([source.find(sep) for sep in ("?", ".", "!") if sep in source] or [len(source)])
    snippet = source[:cut_idx].strip()
    words = snippet.split()
    if len(words) > 10:
        words = words[:10]
    title = " ".join(words).strip()
    if not title:
        title = source[:50].strip()
    if not title:
        return None
    return title[:1].upper() + title[1:]


def generate_chat_title(user_text: Optional[str], agent_text: Optional[str]) -> Optional[str]:
    """Use small_llm to produce a readable chat title with heuristic fallback."""
    if not user_text and not agent_text:
        return None

    base = (user_text or "").strip()
    context = (agent_text or "").strip()
    payload = base
    if context and context not in payload:
        payload = f"User: {base}\nAssistant: {context}" if base else context

    try:
        messages = [
            SystemMessage(content=_TITLE_SYSTEM_PROMPT),
            HumanMessage(content=payload or "Untitled conversation"),
        ]
        response = small_llm.invoke(messages)
        candidate = (getattr(response, "content", "") or "").strip()
        candidate = re.sub(r"[\n\r]+", " ", candidate)
        candidate = candidate.strip('"\' ')
        if candidate:
            if len(candidate) > 80:
                candidate = candidate[:80].rstrip() + "..."
            return candidate
    except Exception:
        pass

    return _fallback_title(user_text, agent_text)
