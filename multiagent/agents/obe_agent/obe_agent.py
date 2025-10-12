import sys
from pathlib import Path
from typing import List

# Add the root directory to the Python path for module imports
root_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

from config import llm
from multiagent.prompts.obe_prompts import CLO_PLO_MAPPING_PROMPT


class OBEAgent:
    """
    An agent specialized in Outcome-Based Education (OBE) to map Course Learning
    Outcomes (CLOs) to Program Learning Outcomes (PLOs).
    """

    def __init__(self):
        """
        Initializes the OBEAgent with a pre-configured LangChain chain.
        """
        self.chain = CLO_PLO_MAPPING_PROMPT | llm

    def run(self, clos: List[str], plos: List[str]) -> str:
        """
        Takes lists of CLOs and PLOs, formats them, and invokes the LLM chain
        to generate a mapping table and justifications.

        Args:
            clos (List[str]): A list of Course Learning Outcomes.
            plos (List[str]): A list of Program Learning Outcomes.

        Returns:
            str: A formatted string containing the markdown mapping table
                 and justifications.
        """
        # Format the lists into numbered strings for the prompt
        clo_str = "\\n".join([f"CLO {i+1}: {clo}" for i, clo in enumerate(clos)])
        plo_str = "\\n".join([f"PLO {i+1}: {plo}" for i, plo in enumerate(plos)])

        # Invoke the chain with the formatted inputs
        response = self.chain.invoke({"clos": clo_str, "plos": plo_str})

        # Return the content of the AI's response
        return response.content


if __name__ == "__main__":
    # Example usage for direct testing
    obe_agent = OBEAgent()

    # Sample CLOs and PLOs for a software engineering program
    sample_clos = [
        "Analyse a complex computing problem and to apply principles of computing and other relevant disciplines to identify solutions.",
        "Design, implement, and evaluate a computing-based solution to meet a given set of computing requirements in the context of the program’s discipline.",
        "Communicate effectively in a variety of professional contexts.",
        "Recognize professional responsibilities and make informed judgments in computing practice based on legal and ethical principles.",
        "Function effectively as a member or leader of a team engaged in activities appropriate to the program’s discipline.",
    ]

    sample_plos = [
        "PLO 1: Academic Education",
        "PLO 2: Knowledge for Solving Computing Problems",
        "PLO 3: Problem Analysis",
        "PLO 4: Design/Development of Solutions",
        "PLO 5: Modern Tool Usage",
        "PLO 6: Individual and Team Work",
        "PLO 7: Communication",
        "PLO 8: Computing Professionalism and Society",
        "PLO 9: Ethics",
        "PLO 10: Life-Long Learning",
    ]

    # Generate the mapping
    mapping_result = obe_agent.run(sample_clos, sample_plos)

    # Print the result
    print(mapping_result)
