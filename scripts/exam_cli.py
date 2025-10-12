#!/usr/bin/env python3
"""
Exam/Quiz Generator CLI (debug-friendly)

This script runs ONLY the exam generator path of CampusHive via the supervisor.
It provides pretty-printed, verbose diagnostics to help troubleshoot routing,
retrieval, and LLM behavior.

Usage examples:
  ./scripts/exam_cli.py --query "Generate a final exam for Data Structures (total 100 marks) with trees and graphs focus" --role faculty
  ./scripts/exam_cli.py -q "Make a 20-mark quiz on TCP congestion control" -r student -v
"""

import os
import sys
import argparse
import asyncio
import uuid
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exam/Quiz Generator (debug)")
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        required=True,
        help="Natural language request for the exam/quiz",
    )
    parser.add_argument(
        "--role",
        "-r",
        type=str,
        choices=["student", "faculty"],
        default="student",
        help="User role to guide generation style",
    )
    parser.add_argument(
        "--session",
        "-s",
        type=str,
        default=None,
        help="Optional session id for memory tracking",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable extra diagnostics (routing, timing)",
    )
    return parser.parse_args()


async def run(query: str, role: str, session_id: str | None, verbose: bool) -> int:
    sid = session_id or f"exam_cli_{uuid.uuid4().hex[:8]}"

    console.print(Panel.fit(
        f"[bold]Exam/Quiz Generator[/bold]\n[dim]session:[/dim] {sid}  [dim]role:[/dim] {role}\n[dim]time:[/dim] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        title="CampusHive",
        border_style="cyan",
    ))

    if verbose:
        console.print(Panel("Routing is expected to go to the 'exam' path via the supervisor classifier (based on your query).",
                            title="Info", border_style="blue"))

    # Verbose mode: enable any extra diagnostics if the ReAct agent uses env flags in the future
    if verbose:
        os.environ["EXAM_AGENT_DEBUG"] = "1"  # retained for backward-compat; harmless if unused

    # Import graph after setting env (kept for backward-compat flags); ReAct exam agent is used exclusively
    from multiagent.graph.supervisor import supervisor_graph  # noqa: E402

    # Build initial state to force exam routing via classifier prompt
    initial_state = {
        "question": query,
        "session_id": sid,
        "user_role": role,
        "route": [],
        "result": "",
        "conversation_history": []
    }

    result_accum = ""
    route_final: list[str] = []
    shown_nodes: set[str] = set()
    printed_result = False
    t0 = datetime.now()
    
    console.print("\n[bold cyan]Generated Exam:[/bold cyan]\n")
    
    try:
        async for event in supervisor_graph.astream_events(initial_state, version="v1"):
            kind = event.get("event")
            node_name = event.get("name")

            if kind == "on_chain_start":
                if node_name in ["router", "exam", "student", "faculty", "direct"] and node_name not in shown_nodes:
                    if verbose:
                        console.print(f"[dim]-> {node_name}[/dim]")
                    shown_nodes.add(node_name)

            elif kind == "on_chain_stream":
                if node_name in ["exam", "student", "faculty", "direct"]:
                    data = event["data"].get("chunk")
                    if data and "result" in data:
                        delta = data["result"][len(result_accum):]
                        if delta and not printed_result:
                            console.print(delta, end="")
                        result_accum = data["result"]

            elif kind == "on_chain_end":
                if node_name in ["exam", "student", "faculty", "direct"]:
                    data = event["data"].get("output")
                    if data and "result" in data:
                        if not printed_result:
                            # Print any remaining content
                            delta = data["result"][len(result_accum):]
                            if delta:
                                console.print(delta)
                            printed_result = True
                        result_accum = data["result"]
                        route_final = data.get("route", [])

    except Exception as e:
        console.print(Panel.fit(str(e), title="Error", border_style="red"))
        return 1
    
    console.print()  # Final newline

    dt = (datetime.now() - t0).total_seconds()

    # Summary panel
    if verbose:
        tbl = Table(title="Run Summary", show_lines=False, expand=True)
        tbl.add_column("Key", style="bold cyan")
        tbl.add_column("Value", style="white")
        tbl.add_row("Duration (s)", f"{dt:.2f}")
        tbl.add_row("Route", " -> ".join(route_final) if route_final else "(unknown)")
        tbl.add_row("Tokens", str(len(result_accum)))
        console.print(tbl)

    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run(args.query, args.role, args.session, args.verbose))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
