import uvicorn
import argparse

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
    
    args = parser.parse_args()

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
        print("Starting CLI mode...")
        # We need to run the async main function from cli.py
        import asyncio
        from app.cli import cli_main
        
        try:
            asyncio.run(cli_main())
        except KeyboardInterrupt:
            print("\nExiting CLI.")
        except Exception as e:
            print(f"An error occurred in the CLI: {e}")

if __name__ == "__main__":
    main()
