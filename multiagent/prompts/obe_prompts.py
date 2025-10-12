from langchain.prompts import PromptTemplate

# Prompt to map CLOs to PLOs and generate a markdown table and justifications
CLO_PLO_MAPPING_PROMPT = PromptTemplate(
    input_variables=["clos", "plos"],
    template="""
You are an expert in Outcome-Based Education (OBE). Your task is to map Course Learning Outcomes (CLOs) to Program Learning Outcomes (PLOs).

You will be given a list of CLOs and a list of PLOs for a specific academic program.

Your goal is to:
1.  Analyze each CLO and determine which PLOs it helps to achieve.
2.  Create a Markdown table that visually represents the mapping. Use '✓' to indicate a mapping.
3.  For each CLO, provide a brief justification for why it maps to the selected PLOs.

**CLOs:**
{clos}

**PLOs:**
{plos}

**Output Format:**

First, provide the mapping table:

| CLO \\ PLO | PLO 1 | PLO 2 | ... |
| :--- | :---: | :---: | :---: |
| CLO 1 |   ✓   |       |  ✓    |
| CLO 2 |       |   ✓   |       |
| ...   |       |       |       |

Then, provide the justifications for each mapping:

**Justifications:**

*   **CLO 1:** Justification for why CLO 1 maps to PLO 1, PLO 3, etc.
*   **CLO 2:** Justification for why CLO 2 maps to PLO 2, etc.
*   ...

---
Begin!
""",
)
