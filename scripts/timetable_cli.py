#!/usr/bin/env python3
"""
Timetable Agent CLI for CampusHive

Interact directly with the TimetableAgent for debugging and manual queries.
"""
import sys
import os
import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from multiagent.agents.timetable_agent import TimetableAgentBuilder

# Default data paths (update if needed)
DEFAULT_TIMETABLE_CSV = os.path.join("data", "structured_timetable.csv")
DEFAULT_MAPPINGS_JSON = os.path.join("data", "mappings.json")

console = Console()

def print_welcome():
    console.print(Panel.fit(
        "[bold blue]CampusHive Timetable Agent CLI[/bold blue]\n\n"
        "Interact directly with the TimetableAgent.\n"
        "Type your query (e.g., 'Give me the timetable for 7th semester AI, electives: Agentic AI, OBL').\n"
        "Type 'exit' or 'quit' to end the session.",
        title="[bold blue]Timetable Debug Mode[/bold blue]",
        border_style="blue"
    ))

def print_timetable_result(result):
    # Try to parse as JSON timetable, else print as plain text
    import json
    try:
        data = json.loads(result)
        if "courses" in data:
            table = Table(title="Timetable Results", show_header=True, header_style="bold magenta")
            table.add_column("Course", style="cyan")
            table.add_column("Room", style="green")
            table.add_column("Time Slot", style="yellow")
            table.add_column("Day", style="magenta")
            for course in data["courses"]:
                table.add_row(
                    course.get("course", "-"),
                    course.get("room_number", "-"),
                    course.get("time_slot", "-"),
                    course.get("day", "-")
                )
            console.print(table)
            return
    except Exception:
        pass
    # Fallback: print as markdown/plain text
    console.print(Markdown(result))

def main():
    parser = argparse.ArgumentParser(description="CampusHive Timetable Agent CLI")
    parser.add_argument("--csv", default=DEFAULT_TIMETABLE_CSV, help="Path to structured_timetable.csv")
    parser.add_argument("--mapping", default=DEFAULT_MAPPINGS_JSON, help="Path to mappings.json")
    args = parser.parse_args()

    # Load timetable agent
    try:
        agent = TimetableAgentBuilder(args.csv, args.mapping)
    except Exception as e:
        console.print(f"[red]Failed to load TimetableAgent: {e}[/red]")
        sys.exit(1)

    print_welcome()
    while True:
        try:
            query = console.input("\n[bold cyan]You:[/bold cyan] ")
            if query.strip().lower() in ["exit", "quit"]:
                console.print("[bold blue]👋 Goodbye![/bold blue]")
                break
            if not query.strip():
                continue
            # Call the agent (simulate as if from wrapper)
            try:
                # TimetableAgentBuilder does not have a direct 'answer' method, so use the agent
                # We'll use the .agent interface (LangGraph ReAct agent)
                from langchain_core.messages import HumanMessage
                msgs = [HumanMessage(content=query)]
                config = {"configurable": {"thread_id": "timetable_cli"}}
                result = ""
                for step in agent.agent.stream({"messages": msgs}, config, stream_mode="values"):
                    if step.get("messages"):
                        last_msg = step["messages"][-1]
                        if hasattr(last_msg, "content") and isinstance(last_msg.content, str):
                            result = last_msg.content
                print_timetable_result(result)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold blue]👋 Goodbye![/bold blue]")
            break

if __name__ == "__main__":
    main()
