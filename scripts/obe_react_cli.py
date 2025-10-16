import sys
import argparse
from pathlib import Path

# Add the root directory to the Python path for module imports
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from langchain_core.messages import HumanMessage
from multiagent.agents.obe_agent.react_obe_agent import OBEReactAgentBuilder


def main():
    parser = argparse.ArgumentParser(
        description="Interactive CLI for OBE ReAct agent with memory."
    )
    parser.add_argument(
        "--session-id",
        dest="session_id",
        default="cli-test",
        help="Session/thread id for memory",
    )
    parser.add_argument(
        "--user-id",
        dest="user_id",
        default="1",
        help="User id for document tools",
        type=str,
    )
    parser.add_argument(
        "--message", dest="message", help="Initial message to send", required=True
    )
    args = parser.parse_args()

    builder = OBEReactAgentBuilder()
    agent = builder.get_agent()

    cfg = {"configurable": {"thread_id": f"obe_react_cli::{args.session_id}"}}

    final_answer = ""
    for step in agent.stream(
        {"messages": [HumanMessage(content=args.message)]}, cfg, stream_mode="values"
    ):
        if step.get("messages"):
            last = step["messages"][-1]
            if hasattr(last, "content") and isinstance(last.content, str):
                final_answer = last.content

    print(final_answer or "")


if __name__ == "__main__":
    main()
