import sys
import argparse
from pathlib import Path

# Add the root directory to the Python path for module imports
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from multiagent.agents.obe_agent.obe_agent import OBEAgent


def main():
    """
    A command-line interface for the OBE Agent to map CLOs to PLOs.
    """
    parser = argparse.ArgumentParser(description="Map CLOs to PLOs using the OBE Agent.")

    # Arguments for CLOs and PLOs
    parser.add_argument(
        "--clos",
        nargs="+",
        required=True,
        help="A list of Course Learning Outcomes (CLOs).",
    )
    parser.add_argument(
        "--plos",
        nargs="+",
        required=True,
        help="A list of Program Learning Outcomes (PLOs).",
    )

    args = parser.parse_args()

    # Initialize the OBE Agent
    obe_agent = OBEAgent()

    # Run the agent with the provided CLOs and PLOs
    print("Generating CLO-PLO mapping...\\n")
    result = obe_agent.run(clos=args.clos, plos=args.plos)

    # Print the final result
    print(result)


if __name__ == "__main__":
    main()
