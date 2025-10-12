#!/usr/bin/env python3
"""
Faculty Agent CLI

Interact with the unified Faculty ReAct agent (tools + semantic search) in streaming or one-shot modes.

Usage examples:
  - One-shot:   ./faculty_agent_cli.py -q "What is Dr. X's email?"
  - Streaming:  ./faculty_agent_cli.py -q "Summarize Prof. Y" --stream
  - REPL:       ./faculty_agent_cli.py

Note: Ensure the correct environment is active and required API keys are set.
"""
import sys
import argparse
from pathlib import Path

# Add repo root to path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from multiagent.agents.faculty_react_agent import FacultyReactAgentBuilder, FacultyAgent  # noqa: E402
from langchain_core.callbacks.base import BaseCallbackHandler  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.markdown import Markdown  # noqa: E402


class DebugHandler(BaseCallbackHandler):
    """Callback handler to print detailed debug info about tool and LLM activity."""

    def __init__(self):
        self.events = []

    # Tool lifecycle
    def on_tool_start(self, serialized, input_str=None, **kwargs):  # type: ignore[override]
        name = (serialized or {}).get("name") or (serialized or {}).get("id")
        msg = f"[DEBUG][TOOL START] {name} input={input_str}"
        print(msg, file=sys.stderr)
        self.events.append({"type": "tool_start", "name": name, "input": input_str})

    def on_tool_end(self, output, **kwargs):  # type: ignore[override]
        try:
            snippet = output if isinstance(output, str) else str(output)
            snippet = snippet[:1200]
        except Exception as e:
            snippet = f"<unprintable output: {e}>"
        msg = f"[DEBUG][TOOL END] output={snippet}"
        print(msg, file=sys.stderr)
        self.events.append({"type": "tool_end", "output": snippet})

    # LLM lifecycle (optional, concise)
    def on_llm_start(self, serialized, prompts, **kwargs):  # type: ignore[override]
        model = (serialized or {}).get("name") or (serialized or {}).get("id")
        print(f"[DEBUG][LLM START] model={model} prompts={len(prompts)}", file=sys.stderr)

    def on_llm_end(self, response, **kwargs):  # type: ignore[override]
        print("[DEBUG][LLM END]", file=sys.stderr)


def one_shot(question: str, session_id: str = "cli") -> str:
    """Run a single question, build context with tools, and return the final LLM answer."""
    builder = FacultyReactAgentBuilder()
    # Mimic builder.stream but return full text
    agent = builder.get_agent()
    config = {"configurable": {"thread_id": f"faculty_react::{session_id}"}}
    last = ""
    for step in agent.stream({"messages": [{"type": "human", "content": question}]}, config, stream_mode="values"):
        msgs = step.get("messages") or []
        if msgs and hasattr(msgs[-1], "content") and isinstance(msgs[-1].content, str):
            last = msgs[-1].content
    # Finalize synchronously
    return builder.fac._finalize_with_llm(question, last, stream=False)  # type: ignore[attr-defined]


def one_shot_basic(question: str) -> str:
    """Run a single question through the basic FacultyAgent (non-ReAct)."""
    fac = FacultyAgent(debug=False)
    return fac.answer(question, stream=False)


def stream_answer(question: str, session_id: str = "cli", debug: bool = False, pretty: bool = True):
    """Stream the final answer; with --debug, also log tool calls and finalization context to stderr."""
    builder = FacultyReactAgentBuilder()
    console = Console()
    if not debug:
        if not pretty:
            for token in builder.stream(question, session_id=session_id):
                print(token, end="", flush=True)
            print()
            return
        # Pretty printing: collect and render as Markdown
        buf = []
        for token in builder.stream(question, session_id=session_id):
            buf.append(token)
        text = "".join(buf)
        console.print(Markdown(text))
        return

    # Debug path: run internal agent with callbacks to capture tools, then stream finalization
    handler = DebugHandler()
    agent = builder.get_agent()
    config = {
        "configurable": {"thread_id": f"faculty_react::{session_id}"},
        "callbacks": [handler],
    }
    last = ""
    for step in agent.stream({"messages": [{"type": "human", "content": question}]}, config, stream_mode="values"):
        msgs = step.get("messages") or []
        if msgs and hasattr(msgs[-1], "content") and isinstance(msgs[-1].content, str):
            last = msgs[-1].content

    # Show the captured context that will be used for finalization
    print("\n[DEBUG] ===== Context for Finalization =====", file=sys.stderr)
    print(last, file=sys.stderr)
    print("[DEBUG] ====================================\n", file=sys.stderr)

    # Stream or pretty-print finalization
    if not pretty:
        for tok in builder.fac._stream_finalize_with_llm(question, last):  # type: ignore[attr-defined]
            print(tok, end="", flush=True)
        print()
    else:
        final_text = builder.fac._finalize_with_llm(question, last, stream=False)  # type: ignore[attr-defined]
        console.print(Markdown(final_text))


def repl(session_id: str = "repl"):
    print("Faculty Agent REPL. Type 'exit' to quit.\n")
    builder = FacultyReactAgentBuilder()
    while True:
        try:
            q = input("You: ").strip()
            if not q:
                continue
            if q.lower() in {"exit", "quit", "q"}:
                print("Goodbye!")
                break
            for token in builder.stream(q, session_id=session_id):
                print(token, end="", flush=True)
            print()
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            print("\nGoodbye!")
            break


def main():
    p = argparse.ArgumentParser(description="Faculty Agent CLI (ReAct + tools)")
    p.add_argument("-q", "--question", type=str, help="Ask a single question and exit")
    p.add_argument("--basic", action="store_true", help="Use the basic FacultyAgent (no ReAct)")
    p.add_argument("--stream", action="store_true", help="Stream tokens to stdout (ReAct mode)")
    p.add_argument("--session", type=str, default="cli", help="Session id for threaded memory")
    p.add_argument("--no-pretty", action="store_true", help="Disable Markdown pretty printing of final answers")
    p.add_argument("--debug", action="store_true", help="Log tool invocations and finalization context to stderr (ReAct mode)")
    args = p.parse_args()

    if args.question:
        console = Console()
        if args.basic:
            ans = one_shot_basic(args.question)
            if args.no_pretty:
                print(ans)
            else:
                console.print(Markdown(ans))
        elif args.stream:
            stream_answer(args.question, session_id=args.session, debug=args.debug, pretty=not args.no_pretty)
        else:
            ans = one_shot(args.question, session_id=args.session)
            if args.no_pretty:
                print(ans)
            else:
                console.print(Markdown(ans))
        return

    repl(session_id=args.session)


if __name__ == "__main__":
    main()
