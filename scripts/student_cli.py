#!/usr/bin/env python3
"""
Student Assistant CLI

Interact with the student routing node which directs queries to:
- General RAG (university info)
- Degree Advisor (tool-enabled)
- Timetable Agent

Usage examples:
  - One-shot:   ./student_cli.py -q "List MS programs in CS"
  - Streaming:  ./student_cli.py -q "What's my Monday timetable?" --stream
  - REPL:       ./student_cli.py

Notes:
- Pretty printing uses Markdown via rich (disable with --no-pretty)
- --debug logs route decisions and tool/LLM activity to stderr
"""
import sys
import argparse
from pathlib import Path
from typing import Optional

# Add repo root to path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from langchain_core.callbacks.base import BaseCallbackHandler  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.markdown import Markdown  # noqa: E402

from config import llm  # noqa: E402
from multiagent.routing.classifiers import classify_student  # noqa: E402
from multiagent.nodes.student import (  # noqa: E402
    run_student,
    run_student_streaming,
)

# Optional imports for deeper debug on specific routes
try:  # degree route
    from multiagent.agents.degree_advisor_agent import DegreeReactAgentBuilder  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover - optional at runtime
    DegreeReactAgentBuilder = None  # type: ignore

try:  # general route debug
    from multiagent.nodes.student import _get_engine  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover
    _get_engine = None  # type: ignore

try:  # timetable route
    from multiagent.agents.timetable_agent import TimetableAgentBuilder  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover
    TimetableAgentBuilder = None  # type: ignore


class DebugHandler(BaseCallbackHandler):
    """Callback handler to print concise debug info about tool and LLM activity."""

    def on_tool_start(self, serialized, input_str=None, **kwargs):  # type: ignore[override]
        name = (serialized or {}).get("name") or (serialized or {}).get("id")
        print(f"[DEBUG][TOOL START] {name} input={input_str}", file=sys.stderr)

    def on_tool_end(self, output, **kwargs):  # type: ignore[override]
        try:
            snippet = output if isinstance(output, str) else str(output)
            snippet = snippet[:1000]
        except Exception as e:
            snippet = f"<unprintable output: {e}>"
        print(f"[DEBUG][TOOL END] output={snippet}", file=sys.stderr)

    def on_llm_start(self, serialized, prompts, **kwargs):  # type: ignore[override]
        model = (serialized or {}).get("name") or (serialized or {}).get("id")
        print(f"[DEBUG][LLM START] model={model} prompts={len(prompts)}", file=sys.stderr)

    def on_llm_end(self, response, **kwargs):  # type: ignore[override]
        print("[DEBUG][LLM END]", file=sys.stderr)


def detect_route(question: str) -> str:
    try:
        return classify_student((question or "").lower(), llm)
    except Exception:
        return "general"


def one_shot(question: str, session_id: str = "cli", debug: bool = False) -> str:
    """Run a single question through the student router and return the final answer."""
    route = detect_route(question)
    if debug:
        print(f"[DEBUG] Route: {route}", file=sys.stderr)
        if route == "general" and _get_engine is not None:
            try:
                eng = _get_engine()
                docs = eng.retrieve(question)
                print(f"[DEBUG] Retrieved {len(docs)} docs for general route", file=sys.stderr)
                for i, d in enumerate(docs[:5], 1):
                    src = d.metadata.get("source") or d.metadata.get("path") or "unknown"
                    prev = (d.page_content or "").strip().replace("\n", " ")[:180]
                    print(f"  [{i}] src={src}\n      {prev}...", file=sys.stderr)
            except Exception as e:
                print(f"[DEBUG] General debug context error: {e}", file=sys.stderr)

    return run_student(question, session_id=session_id)


def stream_answer(
    question: str,
    *,
    session_id: str = "cli",
    debug: bool = False,
    pretty: bool = True,
):
    """Stream the answer for a question. Pretty-print final text when requested."""
    console = Console()
    route = detect_route(question)
    if debug:
        print(f"[DEBUG] Route: {route}", file=sys.stderr)

    # General: we can truly stream tokens
    if route == "general":
        if debug and _get_engine is not None:
            try:
                eng = _get_engine()
                docs = eng.retrieve(question)
                print(f"[DEBUG] Retrieved {len(docs)} docs for general route", file=sys.stderr)
                for i, d in enumerate(docs[:5], 1):
                    src = d.metadata.get("source") or d.metadata.get("path") or "unknown"
                    prev = (d.page_content or "").strip().replace("\n", " ")[:180]
                    print(f"  [{i}] src={src}\n      {prev}...", file=sys.stderr)
            except Exception as e:
                print(f"[DEBUG] General debug context error: {e}", file=sys.stderr)

        if not pretty:
            for chunk in run_student_streaming(question, session_id=session_id):
                print(chunk, end="", flush=True)
            print()
            return
        # Pretty: collect then render as Markdown
        buf = []
        for chunk in run_student_streaming(question, session_id=session_id):
            buf.append(chunk)
        console.print(Markdown("".join(buf)))
        return

    # Degree: stream via LangGraph agent; may produce final text at the end
    if route == "degree" and DegreeReactAgentBuilder is not None:
        builder = DegreeReactAgentBuilder()
        agent = builder.get_agent()
        handler = DebugHandler() if debug else None
        config = {
            "configurable": {"thread_id": f"student_degree_cli::{session_id}"},
        }
        if handler is not None:
            config["callbacks"] = [handler]

        # Build messages to include system prompt
        msgs = [SystemMessage(content=getattr(builder, "system_prompt_text", "")), HumanMessage(content=question)]

        last: Optional[str] = None
        for step in agent.stream({"messages": msgs}, config, stream_mode="values"):
            msgs_out = step.get("messages") or []
            if msgs_out and hasattr(msgs_out[-1], "content") and isinstance(msgs_out[-1].content, str):
                last = msgs_out[-1].content

        text = last or ""
        if not pretty:
            print(text)
        else:
            console.print(Markdown(text))
        return

    # Timetable or any other: fall back to direct streaming helper
    if debug:
        print("[DEBUG] Using direct streaming helper for this route", file=sys.stderr)
    if not pretty:
        for chunk in run_student_streaming(question, session_id=session_id):
            print(chunk, end="", flush=True)
        print()
        return
    buf = []
    for chunk in run_student_streaming(question, session_id=session_id):
        buf.append(chunk)
    Console().print(Markdown("".join(buf)))


def repl(session_id: str = "repl", pretty: bool = False):
    print("Student Assistant REPL. Type 'exit' to quit.\n")
    while True:
        try:
            q = input("You: ").strip()
            if not q:
                continue
            if q.lower() in {"exit", "quit", "q"}:
                print("Goodbye!")
                break
            if not pretty:
                for chunk in run_student_streaming(q, session_id=session_id):
                    print(chunk, end="", flush=True)
                print()
            else:
                buf = []
                for chunk in run_student_streaming(q, session_id=session_id):
                    buf.append(chunk)
                Console().print(Markdown("".join(buf)))
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            print("\nGoodbye!")
            break


def main():
    p = argparse.ArgumentParser(description="Student Assistant CLI (General/ Degree/ Timetable)")
    p.add_argument("-q", "--question", type=str, help="Ask a single question and exit")
    p.add_argument("--stream", action="store_true", help="Stream tokens when possible")
    p.add_argument("--session", type=str, default="cli", help="Session id for threaded memory")
    p.add_argument("--no-pretty", action="store_true", help="Disable Markdown pretty printing of final answers")
    p.add_argument("--debug", action="store_true", help="Log route/tool/LLM debug info to stderr")
    args = p.parse_args()

    if args.question:
        console = Console()
        if args.stream:
            stream_answer(args.question, session_id=args.session, debug=args.debug, pretty=not args.no_pretty)
        else:
            ans = one_shot(args.question, session_id=args.session, debug=args.debug)
            if args.no_pretty:
                print(ans)
            else:
                console.print(Markdown(ans))
        return

    repl(session_id=args.session, pretty=not args.no_pretty)


if __name__ == "__main__":
    main()
