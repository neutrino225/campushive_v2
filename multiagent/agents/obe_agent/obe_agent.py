import sys
from pathlib import Path
from typing import List, Optional, Union, Dict

# Add the root directory to the Python path for module imports
root_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

from config import llm, embeddings
from multiagent.prompts.obe_prompts import CLO_PLO_MAPPING_PROMPT
from multiagent.memory.retriever_manager import get_session_retriever
from multiagent.utils.clo_plo_mapper import CLOPLOMappingEngine


class OBEAgent:
    """
    An agent specialized in Outcome-Based Education (OBE) to map Course Learning
    Outcomes (CLOs) to Program Learning Outcomes (PLOs).

    Enhanced with document upload support for extracting CLOs/PLOs from syllabi
    and course outlines.
    """

    def __init__(self):
        """
        Initializes the OBEAgent with advanced mapping engine and LLM chain.
        """
        self.chain = CLO_PLO_MAPPING_PROMPT | llm
        self.mapping_engine = CLOPLOMappingEngine(embeddings=embeddings)

    def extract_outcomes_from_document(
        self, user_id: int, session_id: str, outcome_type: str = "both"
    ) -> dict:
        """
        Extract CLOs and/or PLOs from uploaded course documents.

        Args:
            user_id: User ID
            session_id: Session ID (string or int)
            outcome_type: Type to extract - "clo", "plo", or "both"

        Returns:
            Dictionary with extracted outcomes:
            {
                "clos": List[str],
                "plos": List[str],
                "raw_text": str
            }
        """
        # Get session retriever
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"[OBE DEBUG] Attempting to retrieve documents: user_id={user_id}, session_id={session_id} (type: {type(session_id)})"
        )
        retriever = get_session_retriever(user_id, session_id)

        if not retriever:
            logger.info(
                f"[OBE DEBUG] No retriever found for user_{user_id}_session_{session_id}"
            )
            return {
                "clos": [],
                "plos": [],
                "error": "No documents uploaded in this session. Please upload a course outline or syllabus first.",
            }

        logger.info(f"[OBE DEBUG] Retriever found! Attempting to retrieve documents...")

        # Query for learning outcomes
        queries = []
        if outcome_type in ["clo", "both"]:
            queries.append(
                "course learning outcomes CLO objectives what students will learn"
            )
        if outcome_type in ["plo", "both"]:
            queries.append(
                "program learning outcomes PLO program objectives competencies"
            )

        # Retrieve relevant chunks
        all_chunks = []
        for query in queries:
            chunks = retriever.get_relevant_documents(query)
            all_chunks.extend(chunks)

        if not all_chunks:
            return {
                "clos": [],
                "plos": [],
                "error": "No learning outcomes found in uploaded documents. The document may not contain CLO/PLO information.",
            }

        # Combine chunks
        combined_text = "\n\n".join([chunk.page_content for chunk in all_chunks[:10]])

        # Use LLM to extract structured outcomes
        extraction_prompt = f"""Extract the learning outcomes from the following course document text.

Document Text:
{combined_text}

Please extract:
1. Course Learning Outcomes (CLOs) - specific to this course
2. Program Learning Outcomes (PLOs) - broader program-level outcomes

Format your response as:
**CLOs:**
1. [First CLO]
2. [Second CLO]
...

**PLOs:**
1. [First PLO]
2. [Second PLO]
...

If a type of outcome is not present, say "Not found in document."
Be precise and extract the exact wording when possible."""

        response = llm.invoke(extraction_prompt)
        extracted_text = response.content

        # Parse the response
        clos = []
        plos = []

        # Extract CLOs
        clo_section = ""
        plo_section = ""

        if "**CLOs:**" in extracted_text:
            parts = extracted_text.split("**PLOs:**")
            clo_section = (
                parts[0].split("**CLOs:**")[1]
                if len(parts[0].split("**CLOs:**")) > 1
                else ""
            )
            plo_section = parts[1] if len(parts) > 1 else ""

        # Parse CLOs
        for line in clo_section.split("\n"):
            line = line.strip()
            if line and not line.startswith("Not found") and not line.startswith("**"):
                # Remove numbering
                cleaned = line.lstrip("0123456789.-) ")
                if cleaned:
                    clos.append(cleaned)

        # Parse PLOs
        for line in plo_section.split("\n"):
            line = line.strip()
            if line and not line.startswith("Not found") and not line.startswith("**"):
                cleaned = line.lstrip("0123456789.-) ")
                if cleaned:
                    plos.append(cleaned)

        return {
            "clos": clos,
            "plos": plos,
            "raw_text": combined_text,
            "extracted_text": extracted_text,
        }

    def improve_outcomes(
        self,
        outcomes: List[str],
        outcome_type: str,
        improvement_focus: str = "clarity and measurability",
    ) -> dict:
        """
        Improve CLOs or PLOs based on OBE best practices.

        Args:
            outcomes: List of learning outcomes to improve
            outcome_type: "CLO" or "PLO"
            improvement_focus: What to focus on (clarity, measurability, Bloom's taxonomy, etc.)

        Returns:
            Dictionary with original and improved outcomes
        """
        if not outcomes:
            return {"error": "No outcomes provided to improve"}

        outcomes_str = "\n".join(
            [f"{i+1}. {outcome}" for i, outcome in enumerate(outcomes)]
        )

        improvement_prompt = f"""You are an expert in Outcome-Based Education (OBE). Improve the following {outcome_type}s.

Current {outcome_type}s:
{outcomes_str}

Improvement Focus: {improvement_focus}

Provide improved versions that:
1. Use clear, measurable action verbs (Bloom's taxonomy)
2. Are specific and observable
3. Follow OBE best practices
4. Align with appropriate cognitive levels

For each outcome, provide:
- Original: [original text]
- Improved: [improved text]
- Rationale: [brief explanation of changes]

Format as:
**{outcome_type} 1:**
- Original: [text]
- Improved: [text]
- Rationale: [explanation]

**{outcome_type} 2:**
...
"""

        response = llm.invoke(improvement_prompt)

        return {
            "original": outcomes,
            "improved_response": response.content,
            "outcome_type": outcome_type,
        }

    def generate_advanced_mapping(
        self,
        clos: Union[List[str], Dict[int, str]],
        plos: Union[List[str], Dict[int, str]],
        threshold: float = 0.4,
        use_llm_refinement: bool = True,
    ) -> str:
        """
        Generate CLO-PLO mapping using advanced multi-strategy approach.

        Combines:
        - Bloom's taxonomy alignment
        - Action verb matching
        - Semantic similarity
        - Keyword overlap
        - Optional LLM refinement

        Args:
            clos: List of CLO texts or dict with int keys
            plos: List of PLO texts or dict with int keys
            threshold: Minimum composite score for mapping (0-1)
            use_llm_refinement: Whether to use LLM for final refinement

        Returns:
            Formatted markdown table with scores and justifications
        """
        if not clos or not plos:
            return "❌ No CLOs or PLOs provided for mapping."

        # Convert dicts to lists if needed
        if isinstance(clos, dict):
            clos = [clos[k] for k in sorted(clos.keys())]
        if isinstance(plos, dict):
            plos = [plos[k] for k in sorted(plos.keys())]

        # Generate mapping using advanced engine
        # Use stricter threshold to avoid noisy links
        mapping = self.mapping_engine.generate_mapping(
            clos, plos, threshold=max(threshold, 0.55)
        )

        # Build markdown table
        markdown_parts = []

        # Header
        markdown_parts.append("# CLO-PLO Mapping (Advanced Multi-Strategy Analysis)")
        markdown_parts.append("\n## Mapping Table\n")

        # Table header
        header = "| CLO \\ PLO |"
        for i in range(len(plos)):
            header += f" PLO {i+1} |"
        markdown_parts.append(header)

        # Separator
        separator = "|:----------|"
        for _ in plos:
            separator += ":----------:|"
        markdown_parts.append(separator)

        # Table rows
        for clo_idx in range(len(clos)):
            row = f"| **CLO {clo_idx+1}** |"

            for plo_idx in range(len(plos)):
                # Check if mapping exists
                mapped = False
                for mapping_info in mapping.get(clo_idx, []):
                    if mapping_info["plo_index"] == plo_idx:
                        score = mapping_info["scores"]["composite"]
                        # Show score with checkmark
                        row += f" ✓ ({score:.2f}) |"
                        mapped = True
                        break

                if not mapped:
                    row += "   |"

            markdown_parts.append(row)

        # Detailed justifications
        markdown_parts.append("\n---\n## Detailed Justifications\n")

        for clo_idx, clo in enumerate(clos):
            markdown_parts.append(f"\n### CLO {clo_idx+1}: {clo}\n")

            if clo_idx in mapping and mapping[clo_idx]:
                # Get CLO Bloom level
                clo_bloom = self.mapping_engine.get_bloom_level(clo)
                clo_verbs = self.mapping_engine.extract_action_verbs(clo)

                markdown_parts.append(
                    f"**Bloom's Level**: {clo_bloom[0].title()} (Level {clo_bloom[1]})"
                )
                markdown_parts.append(
                    f"**Action Verbs**: {', '.join(clo_verbs) if clo_verbs else 'None identified'}\n"
                )

                markdown_parts.append("**Mapped PLOs**:\n")

                for mapping_info in mapping[clo_idx]:
                    plo_idx = mapping_info["plo_index"]
                    plo = plos[plo_idx]

                    markdown_parts.append(f"\n#### → PLO {plo_idx+1}: {plo}\n")

                    # Generate justification
                    justification = self.mapping_engine.generate_justification(
                        clo, plo, mapping_info
                    )
                    markdown_parts.append(justification)
            else:
                markdown_parts.append(
                    "⚠️ **No strong mappings found** (all scores below threshold)"
                )

        # Scoring methodology explanation
        markdown_parts.append("\n---\n## Scoring Methodology\n")
        markdown_parts.append(
            """
This mapping uses a **composite scoring system** that combines four strategies:

1. **Bloom's Taxonomy Alignment (30%)**: Evaluates cognitive level compatibility between CLO and PLO
2. **Action Verb Overlap (25%)**: Measures shared action verbs indicating similar competencies
3. **Keyword Similarity (20%)**: Analyzes domain-specific terminology overlap
4. **Semantic Similarity (25%)**: Uses embeddings to measure conceptual alignment

**Composite Score Interpretation**:
- **0.70 - 1.00**: Strong mapping (highly aligned)
- **0.50 - 0.69**: Moderate mapping (good alignment)
- **0.40 - 0.49**: Weak mapping (some alignment)
- **< 0.40**: No mapping (insufficient alignment)

**Threshold**: {threshold} (only mappings above this score are shown)
""".format(
                threshold=threshold
            )
        )

        result = "\n".join(markdown_parts)

        # Optional: LLM refinement for narrative justification
        if use_llm_refinement:
            refinement_prompt = f"""You are an OBE expert. Review this CLO-PLO mapping analysis and provide a brief executive summary.

{result}

Provide a 2-3 paragraph summary that:
1. Highlights the overall alignment quality
2. Notes any CLOs with particularly strong or weak mappings
3. Suggests any improvements if needed

Keep it concise and actionable."""

            try:
                llm_response = llm.invoke(refinement_prompt)
                summary = (llm_response.content or "").strip()
                # Guard against hallucinated extra PLO indices or unrelated content
                if summary and len(summary) < 2500:
                    markdown_parts.insert(1, f"\n## Executive Summary\n\n{summary}\n")
                    result = "\n".join(markdown_parts)
            except Exception:
                pass

        return result

    def run(
        self,
        clos: List[str],
        plos: List[str],
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Takes lists of CLOs and PLOs, formats them, and invokes the LLM chain
        to generate a mapping table and justifications.

        If CLOs/PLOs are empty and session info is provided, attempts to extract
        from uploaded documents.

        Args:
            clos (List[str]): A list of Course Learning Outcomes.
            plos (List[str]): A list of Program Learning Outcomes.
            user_id (Optional[int]): User ID for document retrieval
            session_id (Optional[str]): Session ID for document retrieval

        Returns:
            str: A formatted string containing the markdown mapping table
                 and justifications.
        """
        # If no CLOs/PLOs provided, try to extract from documents
        if (not clos or not plos) and user_id and session_id:
            extraction_result = self.extract_outcomes_from_document(user_id, session_id)

            if "error" in extraction_result:
                return f"❌ {extraction_result['error']}"

            if not clos and extraction_result["clos"]:
                clos = extraction_result["clos"]
            if not plos and extraction_result["plos"]:
                plos = extraction_result["plos"]

        if not clos or not plos:
            return "❌ No CLOs or PLOs available. Please provide them or upload a course document containing learning outcomes."

        # Use advanced mapping with multi-strategy approach
        return self.generate_advanced_mapping(
            clos=clos, plos=plos, threshold=0.55, use_llm_refinement=True
        )


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
