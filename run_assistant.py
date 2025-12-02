import uvicorn
import argparse
import os

# Patch posthog to fix ChromaDB compatibility issue with PostHog 6.x+
try:
    import posthog
    original_capture = posthog.capture
    def patched_capture(*args, **kwargs):
        # Completely silence telemetry
        return
    posthog.capture = patched_capture
except ImportError:
    pass

# Disable ChromaDB telemetry to prevent posthog errors
os.environ["ANONYMIZED_TELEMETRY"] = "False"

def main():
    """
    Main entry point to run the CampusHive application.
    Parses command-line arguments to either run the FastAPI server
    or the command-line interface (CLI).
    """
    parser = argparse.ArgumentParser(description="Run the CampusHive Assistant")
    parser.add_argument(
        "--mode",
        choices=["server", "cli"],
        default="server",
        help="Mode to run the application in: 'server' (FastAPI) or 'cli'."
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for the FastAPI server."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the FastAPI server."
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reloading for the server (for development)."
    )
    parser.add_argument(
        "--debug-graph",
        action="store_true",
        help="When running in CLI mode, show detailed graph events and state for debugging.",
    )
    
    # Role selection for CLI mode
    role_group = parser.add_mutually_exclusive_group()
    role_group.add_argument(
        "-s", "--student",
        action="store_true",
        help="Run CLI in student mode (default)."
    )
    role_group.add_argument(
        "-f", "--faculty",
        action="store_true",
        help="Run CLI in faculty mode."
    )
    
    args = parser.parse_args()
    
    # Determine user role
    user_role = "faculty" if args.faculty else "student"

    if args.mode == "server":
        print(f"Starting FastAPI server on localhost:{args.port}")
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="info"
        )
    elif args.mode == "cli":
        print(f"Starting CLI mode as {user_role}...")
        # We need to run the async main function from cli.py
        import asyncio
        from app.cli import cli_main
        
        try:
            # Pass debug flag and user role into the CLI main
            asyncio.run(cli_main(debug_graph=args.debug_graph, user_role=user_role))
        except KeyboardInterrupt:
            print("\nExiting CLI.")
        except Exception as e:
            print(f"An error occurred in the CLI: {e}")

if __name__ == "__main__":
    main()
