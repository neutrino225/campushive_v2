"""Session context provider for tools to implicitly access user_id and session_id.

This uses thread-local storage so that nodes can set the current (user_id, session_id)
right before invoking an agent, and tool functions can read them without explicitly
passing arguments from the frontend.
"""

from __future__ import annotations
import threading
from typing import Optional, Tuple

_local = threading.local()


def set_current(user_id: Optional[int], session_id: Optional[str]) -> None:
    _local.user_id = user_id
    _local.session_id = str(session_id) if session_id is not None else None


def get_current() -> Tuple[Optional[int], Optional[str]]:
    user_id = getattr(_local, "user_id", None)
    session_id = getattr(_local, "session_id", None)
    return user_id, session_id
