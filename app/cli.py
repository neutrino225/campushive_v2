import os
import sys
import asyncio
import readline
from rich.console import Console
from rich.markdown import Markdown

# Add root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from multiagent.graph.supervisor import supervisor_graph

console = Console()

def print_welcome_message():
    """Prints a welcome message to the console."""
    console.print(Markdown("# Welcome to the CampusHive CLI!"))
    console.print("Ask any question about the university, and the multi-agent system will assist you.")
    console.print("Type 'exit' or 'quit' to end the session.")
    console.print("-" * 50)

async def handle_send(question: str, session_id: str = "cli_session"):
    """Handles sending a question to the supervisor and streaming the response."""
    console.print("\n[bold cyan]CampusHive:[/bold cyan]", end=" ")
    full_response = ""
    route = []
    printed_response = False  # Track if we've already printed the response
    shown_nodes = set()  # Track which nodes we've already shown in the routing display
    
    try:
        # Initialize state with session information
        initial_state = {
            "question": question,
            "session_id": session_id,
            "route": [],
            "result": "",
            "conversation_history": []
        }
        
        async for event in supervisor_graph.astream_events(initial_state, version="v1"):
            kind = event["event"]
            if kind == "on_chain_end":
                node_name = event["name"]
                if node_name in ["student", "faculty", "direct"]:
                    data = event["data"].get("output")
                    if data and "result" in data:
                        full_response = data["result"]
                        route = data.get("route", [])
                        # Only print the response if we haven't already printed it
                        if not printed_response:
                            console.print(full_response)
                            printed_response = True
            elif kind == "on_chain_start":
                node_name = event["name"]
                if node_name in ["student", "faculty", "direct", "router"]:
                    # Only show each node once in the routing display
                    node_key = f"{node_name}"
                    if node_key not in shown_nodes:
                        console.print(f"-> [italic]{node_name}[/italic]", end=" ")
                        shown_nodes.add(node_key)
        
        # Store conversation in memory
        if full_response:
            from multiagent.memory import memory_manager
            memory_manager.add_turn(session_id, question, full_response, route)
        
        if route:
            console.print(f"\n[bold dim]Route: {' -> '.join(route)}[/bold dim]")

    except Exception as e:
        console.print(f"\n[bold red]An error occurred:[/bold red] {e}")


async def cli_main():
    """
    The main asynchronous loop for the command-line interface.
    """
    print_welcome_message()
    
    # Generate a unique session ID for this CLI session
    import uuid
    session_id = f"cli_{uuid.uuid4().hex[:8]}"
    console.print(f"[dim]Session ID: {session_id}[/dim]")
    console.print("[dim]Commands: 'exit' to quit, 'clear' to clear history, 'history' to show conversation[/dim]")
    
    loop = asyncio.get_event_loop()

    while True:
        try:
            # Use prompt_toolkit or just input for simplicity
            question = await loop.run_in_executor(None, lambda: input("You: "))
            
            if question.lower() in ['exit', 'quit']:
                console.print("Goodbye!")
                break
            
            if question.lower() == 'clear':
                from multiagent.memory import memory_manager
                memory_manager.clear_session(session_id)
                console.print("[green]Conversation history cleared![/green]")
                console.print("-" * 50)
                continue
            
            if question.lower() == 'history':
                from multiagent.memory import memory_manager
                history = memory_manager.get_history(session_id)
                if history:
                    console.print("\n[bold]Conversation History:[/bold]")
                    for i, turn in enumerate(history, 1):
                        console.print(f"[dim]{i}. User:[/dim] {turn.user_message}")
                        console.print(f"[dim]   Bot:[/dim] {turn.agent_response}")
                        if turn.route:
                            console.print(f"[dim]   Route:[/dim] {' -> '.join(turn.route)}")
                        console.print()
                else:
                    console.print("[dim]No conversation history yet.[/dim]")
                console.print("-" * 50)
                continue
            
            if not question.strip():
                continue

            await handle_send(question, session_id)

            console.print("-" * 50)

        except (KeyboardInterrupt, EOFError):
            console.print("\nGoodbye!")
            break

if __name__ == "__main__":
    try:
        asyncio.run(cli_main())
    except Exception as e:
        console.print(f"\n[bold red]A fatal error occurred:[/bold red] {e}")
