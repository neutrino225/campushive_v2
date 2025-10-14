#!/usr/bin/env python3
"""
Debug CLI for CampusHive - Shows internal routing decisions, tool calls, and planning mode.
"""
import os
import sys
import asyncio
import readline
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

# Add root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from multiagent.graph.supervisor import run_supervisor_async

console = Console()


def print_welcome_message():
    """Prints a welcome message to the console."""
    console.print(
        Panel.fit(
            "[bold blue]🔍 CampusHive Debug CLI[/bold blue]\n\n"
            "This CLI shows internal routing decisions, planning mode reasoning, and agent handoffs.\n"
            "Ask any question about the university, and see how the multi-agent system works internally.\n\n"
            "[bold yellow]Features:[/bold yellow]\n"
            "• 🧠 Planning Mode: See ReAct reasoning steps and scratchpad\n"
            "• 🤔 Human-in-the-Loop: Interactive clarification requests\n"
            "• 🔀 Routing Visualization: Agent delegation paths\n"
            "• 💾 Memory Tracking: Conversation history management\n\n"
            "[bold]Commands:[/bold]\n"
            "• 'exit' or 'quit' - End session\n"
            "• 'clear' - Clear conversation history\n"
            "• 'history' - Show conversation log\n"
            "• 'mode' - Toggle enhanced/legacy debug mode\n",
            title="[bold blue]🎓 Enhanced Debug Mode[/bold blue]",
            border_style="blue",
        )
    )


async def handle_send_debug(question: str, session_id: str = "debug_session", user_role: str = "student", user_input_mode: bool = False):
    """Handles sending a question with detailed debugging output for both legacy and planning modes."""
    console.print(f"\n[bold cyan]🤔 User Question:[/bold cyan] {question}")
    
    if user_input_mode:
        console.print(f"[dim]   ↳ Resuming from user input (HITL continuation)[/dim]")

    # Track routing steps
    routing_steps = []
    full_response = ""
    route = []
    scratchpad = []
    is_planning_mode = False
    awaiting_user_input = False

    try:
        # Use the enhanced run_supervisor_async which handles planning mode
        console.print(f"\n[bold blue]🚀 Executing Query...[/bold blue]")
        console.print(f"   [cyan]Session:[/cyan] {session_id}")
        console.print(f"   [cyan]User Role:[/cyan] {user_role}")
        console.print(f"   [cyan]User Input Mode:[/cyan] {user_input_mode}")
        
        # Call the supervisor
        result = await run_supervisor_async(
            question=question,
            session_id=session_id,
            user_role=user_role,
            user_input_mode=user_input_mode
        )
        
        # Extract results
        full_response = result.get("response", result.get("result", ""))
        route = result.get("route", [])
        scratchpad = result.get("scratchpad", [])
        is_planning_mode = result.get("planning_mode", False)
        awaiting_user_input = result.get("awaiting_user_input", False)
        
        # Display complexity detection
        if is_planning_mode:
            console.print(f"\n[bold magenta]🧠 Planning Mode Activated[/bold magenta]")
            console.print(f"   [dim]Complex query detected - using ReAct agent with human-in-the-loop[/dim]")
        else:
            console.print(f"\n[bold blue]⚡ Simple Mode[/bold blue]")
            console.print(f"   [dim]Direct routing to appropriate agent[/dim]")
        
        # Display scratchpad if present (planning mode)
        if scratchpad:
            console.print(f"\n[bold yellow]📝 Planning Scratchpad (Reasoning Steps):[/bold yellow]")
            scratchpad_tree = Tree("🧠 Agent Thinking Process")
            for i, step in enumerate(scratchpad, 1):
                scratchpad_tree.add(f"[cyan]Step {i}:[/cyan] {step}")
            console.print(scratchpad_tree)
        
        # Display routing information
        if route:
            console.print(f"\n[bold magenta]🔀 Routing Path:[/bold magenta]")
            route_tree = Tree("🗺️ Agent Path")
            for i, step in enumerate(route, 1):
                if "error" in step.lower():
                    route_tree.add(f"[red]❌ {step}[/red]")
                elif "completed" in step.lower():
                    route_tree.add(f"[green]✅ {step}[/green]")
                elif "streaming" in step.lower():
                    route_tree.add(f"[yellow]⏳ {step}[/yellow]")
                else:
                    route_tree.add(f"[cyan]→ {step}[/cyan]")
            console.print(route_tree)
        
        # Check if waiting for user input
        if awaiting_user_input:
            console.print(f"\n[bold red]⏸️  AWAITING USER INPUT[/bold red]")
            console.print(Panel(
                f"[yellow]{full_response}[/yellow]",
                title="🤔 Agent Needs Your Input",
                border_style="yellow"
            ))
            console.print(f"[dim]↳ Your next message will continue the conversation[/dim]")
            
            # Don't save to memory yet - waiting for user input
            return "awaiting_input"
        
        # Display final response
        console.print(f"\n[bold green]💬 Final Response:[/bold green]")
        response_panel = Panel(
            Markdown(full_response),
            title="🤖 CampusHive Assistant",
            border_style="green"
        )
        console.print(response_panel)
        
        # Display route summary
        console.print(f"\n[dim]🏁 Complete Route: {' → '.join(route)}[/dim]")
        
        # Memory is already saved by run_supervisor_async
        console.print(f"[dim]✅ Conversation turn saved to memory[/dim]")
        
        return "success"

    except Exception as e:
        console.print(f"\n[bold red]❌ An error occurred:[/bold red] {e}")
        import traceback
        console.print(Panel(
            f"[red]{traceback.format_exc()}[/red]",
            title="💥 Error Details",
            border_style="red"
        ))
        return "error"


async def handle_send_debug_legacy(question: str, session_id: str = "debug_session", user_role: str = "student"):
    """Legacy debug handler using direct supervisor_graph streaming (for comparison)."""
    from multiagent.graph.supervisor import supervisor_graph
    
    console.print(f"\n[bold cyan]🤔 User Question:[/bold cyan] {question}")
    console.print(f"[dim]   ↳ Using legacy supervisor_graph.astream_events()[/dim]")

    # Create a table for routing decisions
    route_table = Table(title="🔀 Agent Routing Decisions", show_header=True, header_style="bold magenta")
    route_table.add_column("Step", style="dim", width=12)
    route_table.add_column("Agent", style="bold cyan", width=15)
    route_table.add_column("Decision", style="yellow", width=50)
    route_table.add_column("Details", style="green", width=30)

    # Track routing steps
    routing_steps = []
    full_response = ""
    route = []
    tool_calls = []

    try:
        # Initialize state with session information
        initial_state = {
            "question": question,
            "session_id": session_id,
            "route": [],
            "result": "",
            "conversation_history": [],
            "user_role": user_role,
            "messages": [],
        }

        console.print(f"\n[bold blue]📊 Initial State:[/bold blue]")
        console.print(f"   [cyan]Question:[/cyan] {question}")
        console.print(f"   [cyan]Session:[/cyan] {session_id}")
        console.print(f"   [cyan]User Role:[/cyan] {user_role}")
        console.print(f"   [cyan]Route:[/cyan] {initial_state['route']}")

        event_count = 0
        async for event in supervisor_graph.astream_events(initial_state, version="v1"):
            event_count += 1
            kind = event["event"]
            node_name = event.get("name", "unknown")

            console.print(f"\n[dim]📦 Event {event_count}:[/dim] [bold]{kind}[/bold] on [italic]{node_name}[/italic]")

            if kind == "on_chain_start":
                if node_name in ["supervisor", "main_supervisor"]:
                    console.print("   🎯 [bold blue]Supervisor activated[/bold blue] - Analyzing question for routing...")
                elif node_name in ["student_supervisor", "faculty", "exam", "obe", "direct"]:
                    console.print(f"   🤖 [bold green]{node_name.title()} agent activated[/bold green] - Processing request...")

            elif kind == "on_chain_end":
                if node_name in ["supervisor", "main_supervisor"]:
                    console.print("   ✅ [bold blue]Supervisor completed routing decision[/bold blue]")
                elif node_name in ["student_supervisor", "faculty", "exam", "obe", "direct"]:
                    data = event["data"].get("output", {})
                    if data and "result" in data:
                        result = data["result"]
                        agent_route = data.get("route", [])
                        console.print(f"   🎉 [bold green]{node_name.title()} agent completed[/bold green]")
                        console.print(f"      [cyan]Result:[/cyan] {result[:100]}{'...' if len(result) > 100 else ''}")
                        console.print(f"      [cyan]Route:[/cyan] {' -> '.join(agent_route)}")

                        full_response = result
                        route = agent_route

                        routing_steps.append({
                            "step": f"Step {len(routing_steps)+1}",
                            "agent": node_name.title(),
                            "decision": f"Processed: {question[:30]}{'...' if len(question) > 30 else ''}",
                            "details": f"Response: {len(result)} chars"
                        })

            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                console.print(f"   🔧 [bold yellow]Tool started:[/bold yellow] {tool_name}")
                tool_calls.append(f"Started: {tool_name}")

            elif kind == "on_tool_end":
                tool_name = event.get("name", "unknown")
                console.print(f"   ✅ [bold yellow]Tool completed:[/bold yellow] {tool_name}")
                tool_calls.append(f"Completed: {tool_name}")

            if kind in ["on_chain_end", "on_tool_end"] and node_name in ["supervisor", "main_supervisor", "student_supervisor", "faculty", "exam", "obe"]:
                data = event.get("data", {})
                if data:
                    console.print(f"   [dim]Event data keys: {list(data.keys())}[/dim]")

        if routing_steps:
            console.print(f"\n[bold magenta]📋 Final Routing Summary:[/bold magenta]")
            for step in routing_steps:
                route_table.add_row(step["step"], step["agent"], step["decision"], step["details"])
            console.print(route_table)

        if tool_calls:
            console.print(f"\n[bold yellow]🔧 Tool Calls Made:[/bold yellow]")
            for i, tool_call in enumerate(tool_calls, 1):
                console.print(f"   {i}. {tool_call}")

        console.print(f"\n[bold green]💬 Final Response:[/bold green]")
        console.print(f"[green]{full_response}[/green]")

        if route:
            console.print(f"\n[dim]🏁 Complete Route: {' -> '.join(route)}[/dim]")

        if full_response:
            from multiagent.memory import memory_manager
            memory_manager.add_turn(session_id, question, full_response, route)

    except Exception as e:
        console.print(f"\n[bold red]❌ An error occurred:[/bold red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


async def cli_main(user_role: str = "student", mode: str = "enhanced"):
    """
    The main asynchronous loop for the debug command-line interface.
    
    Args:
        user_role: User role (student, faculty, admin)
        mode: Debug mode ("enhanced" for planning support, "legacy" for direct graph streaming)
    """
    print_welcome_message()

    import uuid
    session_id = f"debug_{uuid.uuid4().hex[:8]}"
    console.print(f"[dim]Session ID:[/dim] [yellow]{session_id}[/yellow]")
    console.print(f"[dim]User Role:[/dim] [yellow]{user_role.upper()}[/yellow]")
    console.print(f"[dim]Debug Mode:[/dim] [yellow]{mode.upper()}[/yellow]")
    console.print("[dim]Commands: 'exit' to quit, 'clear' to clear history, 'history' to show conversation, 'mode' to toggle debug mode[/dim]")
    
    # Track if we're waiting for user input (HITL)
    awaiting_user_input = False

    while True:
        try:
            # Use Rich for colored input prompt
            if awaiting_user_input:
                question = console.input("\n[bold yellow]Your Response:[/bold yellow] ")
            else:
                question = console.input("\n[bold cyan]You:[/bold cyan] ")

            if question.lower() in ["exit", "quit"]:
                console.print("\n[bold blue]👋 Goodbye![/bold blue]")
                break

            if question.lower() == "clear":
                from multiagent.memory import memory_manager
                memory_manager.clear_session(session_id)
                console.print("[green]🧹 Conversation history cleared![/green]")
                awaiting_user_input = False
                continue

            if question.lower() == "history":
                from multiagent.memory import memory_manager
                history = memory_manager.get_history(session_id)
                if history:
                    console.print("\n[bold]📚 Conversation History:[/bold]")
                    for i, turn in enumerate(history, 1):
                        console.print(f"[dim]{i}. [cyan]User:[/cyan][/dim] {turn.user_message}")
                        console.print(f"[dim]   [green]Bot:[/green][/dim] {turn.agent_response[:100]}{'...' if len(turn.agent_response) > 100 else ''}")
                        if turn.route:
                            console.print(f"[dim]   [yellow]Route:[/yellow][/dim] {' -> '.join(turn.route)}")
                        console.print()
                else:
                    console.print("[dim]📝 No conversation history yet.[/dim]")
                continue
            
            if question.lower() == "mode":
                mode = "legacy" if mode == "enhanced" else "enhanced"
                console.print(f"[green]✅ Switched to {mode.upper()} mode[/green]")
                continue

            if not question.strip():
                continue

            # Use appropriate debug handler based on mode
            if mode == "enhanced":
                status = await handle_send_debug(
                    question, 
                    session_id, 
                    user_role=user_role,
                    user_input_mode=awaiting_user_input
                )
                
                # Update HITL state
                if status == "awaiting_input":
                    awaiting_user_input = True
                    console.print(f"\n[yellow]⏳ Waiting for your response to continue...[/yellow]")
                else:
                    awaiting_user_input = False
            else:
                await handle_send_debug_legacy(question, session_id, user_role=user_role)
                awaiting_user_input = False

        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold blue]👋 Goodbye![/bold blue]")
            break


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="CampusHive Debug CLI with planning mode support")
    parser.add_argument("--role", choices=["student", "faculty", "admin"], default="student", 
                       help="User role (default: student)")
    parser.add_argument("--mode", choices=["enhanced", "legacy"], default="enhanced",
                       help="Debug mode: enhanced (planning support) or legacy (direct streaming)")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(cli_main(user_role=args.role, mode=args.mode))
    except Exception as e:
        console.print(f"\n[bold red]💥 A fatal error occurred:[/bold red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
