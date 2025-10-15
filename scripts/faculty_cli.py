"""
Faculty CLI
===========

Purpose:
- Validate OBE document extraction and CLO-PLO mapping against existing session vector stores.
- Use immutable DB session ID and user ID explicitly to isolate UI integration issues.

Capabilities:
- verify: Check if the session vector store exists and how many vectors it contains.
- extract: Use OBEAgent to extract CLOs/PLOs from uploaded documents.
- map: Extract and generate a CLO→PLO mapping using the advanced engine.
- chat: Optionally invoke the supervisor graph for a question with the provided session/user context.

Usage examples:
  python scripts/faculty_cli.py verify --user-id 6 --session-id 437
  python scripts/faculty_cli.py extract --user-id 6 --session-id 437 --type both
  python scripts/faculty_cli.py map --user-id 6 --session-id 437
  python scripts/faculty_cli.py chat --user-id 6 --session-id 437 --question "Extract CLOs from uploaded document"

Notes:
- This script runs locally and does NOT require the FastAPI server.
- It uses the same vector store layout as the backend: data/vector_stores/user_uploads/user_{user_id}_session_{session_id}
"""

import os
import sys
import argparse
import logging
import asyncio
from typing import Optional

from pathlib import Path

# Ensure project root on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import embeddings, llm  # noqa: E402
from multiagent.agents.obe_agent.obe_agent import OBEAgent  # noqa: E402
from multiagent.memory.retriever_manager import (  # noqa: E402
    get_session_retriever_manager,
    get_session_retriever,
)


# Optional: supervisor chat for end-to-end route testing
async def _maybe_run_supervisor(question: str, session_id: str, user_id: int) -> dict:
    try:
        from multiagent.graph.supervisor import run_supervisor_async
    except Exception as e:
        return {"error": f"Supervisor not available: {e}"}

    # Minimal run; supervisor handles routing; DB persistence is not required here
    try:
        result = await run_supervisor_async(
            question,
            session_id,
            current_user=None,  # Not needed for routing; state carries ids
            db=None,
            extra_state={
                "user_id": user_id,
                "session_id": str(session_id),
            },
        )
        return result
    except Exception as e:
        return {"error": f"Supervisor error: {e}"}


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def get_store_info(user_id: int, session_id: str) -> dict:
    manager = get_session_retriever_manager(embeddings=embeddings)
    store_path = manager.get_session_store_path(user_id, str(session_id))

    info = {
        "store_path": store_path,
        "exists": os.path.exists(store_path),
        "doc_count": 0,
        "error": None,
    }

    if not info["exists"]:
        return info

    try:
        # Directly open the Chroma store to inspect count
        from langchain_community.vectorstores import Chroma

        vs = Chroma(persist_directory=store_path, embedding_function=embeddings)
        # Access private attribute for troubleshooting purposes only
        info["doc_count"] = int(vs._collection.count())
    except Exception as e:
        info["error"] = str(e)

    return info


def cmd_verify(args: argparse.Namespace) -> int:
    user_id = args.user_id
    session_id = str(args.session_id)
    info = get_store_info(user_id, session_id)

    print("\nVector Store Check")
    print("------------------")
    print(f"Path       : {info['store_path']}")
    print(f"Exists     : {info['exists']}")
    print(f"Doc Count  : {info['doc_count']}")
    if info["error"]:
        print(f"Error      : {info['error']}")

    # Try to get a retriever via the same helper the agent uses
    retriever = get_session_retriever(user_id, session_id)
    print(f"Retriever  : {'OK' if retriever else 'None'}")

    return 0 if info["exists"] else 1


def cmd_extract(args: argparse.Namespace) -> int:
    user_id = args.user_id
    session_id = str(args.session_id)
    outcome_type = args.type

    agent = OBEAgent()
    print("\nExtracting Outcomes")
    print("-------------------")
    print(f"user_id={user_id} session_id={session_id} type={outcome_type}")

    result = agent.extract_outcomes_from_document(user_id=user_id, session_id=session_id, outcome_type=outcome_type)

    if result.get("error"):
        print(f"Error: {result['error']}")
        return 2

    clos = result.get("clos") or []
    plos = result.get("plos") or []

    print(f"Found CLOs ({len(clos)}):")
    for i, clo in enumerate(clos, 1):
        print(f"  {i}. {clo}")

    print(f"\nFound PLOs ({len(plos)}):")
    for i, plo in enumerate(plos, 1):
        print(f"  {i}. {plo}")

    return 0 if clos or plos else 3


def cmd_map(args: argparse.Namespace) -> int:
    user_id = args.user_id
    session_id = str(args.session_id)

    agent = OBEAgent()
    print("\nCLO→PLO Mapping")
    print("---------------")
    print(f"user_id={user_id} session_id={session_id}")

    ext = agent.extract_outcomes_from_document(user_id=user_id, session_id=session_id, outcome_type="both")
    if ext.get("error"):
        print(f"Extraction error: {ext['error']}")
        return 2

    clos = ext.get("clos") or []
    plos = ext.get("plos") or []
    print(f"Extracted CLOs: {len(clos)} | PLOs: {len(plos)}")
    if not clos or not plos:
        print("Not enough outcomes to map. Provide a document with both CLOs and PLOs.")
        return 3

    mapping = agent.run(clos=clos, plos=plos, user_id=user_id, session_id=session_id)
    print("\n=== Mapping Result (first 1200 chars) ===\n")
    print(mapping[:1200])
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    user_id = args.user_id
    session_id = str(args.session_id)
    question = args.question

    print("\nSupervisor Chat")
    print("---------------")
    print(f"user_id={user_id} session_id={session_id}\nQ: {question}\n")

    result = asyncio.run(_maybe_run_supervisor(question, session_id, user_id))
    if "error" in result:
        print(f"Error: {result['error']}")
        return 2

    route = result.get("route")
    response = result.get("response")
    print(f"Route   : {route}")
    print(f"Response: {response[:1200] if response else ''}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Faculty CLI for OBE extraction and mapping")
    p.add_argument("command", choices=["verify", "extract", "map", "chat"], help="Command to run")
    p.add_argument("--user-id", type=int, required=True, help="User ID owning the session")
    p.add_argument("--session-id", type=str, required=True, help="Immutable session ID (DB id)")
    p.add_argument("--type", choices=["clo", "plo", "both"], default="both", help="Extraction type for extract command")
    p.add_argument("--question", type=str, help="Question for chat command")
    p.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    if args.command == "verify":
        return cmd_verify(args)
    elif args.command == "extract":
        return cmd_extract(args)
    elif args.command == "map":
        return cmd_map(args)
    elif args.command == "chat":
        if not args.question:
            print("--question is required for chat command")
            return 2
        return cmd_chat(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
