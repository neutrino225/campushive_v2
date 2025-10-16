import argparse
import json
from pathlib import Path  # Ensure Path is used for file operations
from pdb import run
from typing import Dict, Any, Optional, List, Tuple
import asyncio

import os
import sys

# --- Environment Setup ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# --- Imports (Assuming these exist and are configured) ---
from multiagent.prompts import evaluation_prompts
from config import llm
from multiagent.graph.supervisor import supervisor_graph

# --- Constants ---
# NOTE: Using the JSON-enforced prompts from the previous turn here!
# Assuming evaluation_prompts module contains the final, JSON-enforced versions.
PROMPT_KEYS: List[Tuple[str, str]] = [
    ("conciseness", evaluation_prompts.CONCISENESS_PROMPT),
    ("helpfullness", evaluation_prompts.HELPFULLNESS_PROMPT),
    ("hallucination", evaluation_prompts.HALLUCINATION_PROMPT),
    ("toxicity", evaluation_prompts.TOXICITY_PROMPT),
    ("relevance", evaluation_prompts.RELEVANCE_PROMPT),
]

# --- Queries (Unchanged) ---
queries_for_agents = {
    "Exam Agent": [
        "Create a final exam for the course ‘Database Systems’ with 10 MCQs, 5 short questions, and 2 long questions, ensuring balanced difficulty.",
        "Generate a quiz for ‘Software Project Management’ focused only on Agile and Scrum concepts.",
        "Prepare a midterm exam for ‘Computer Networks’ using the question bank, avoiding repetition of previous exam questions.",
        "Create a personalized practice quiz for ‘Data Structures’ focusing on trees and graphs with instant feedback.",
        "Generate a mock exam for ‘Database Systems’ similar in pattern to the last midterm.",
    ],
    "OBE Agent": [
        "Validate the CLO-PLO mapping for the course ‘Operating Systems’ and identify any mismatched or weakly aligned outcomes.",
        "Generate a CLO-PLO correlation report for the BS Artificial Intelligence program according to HEC standards.",
        "Suggest improvements for PLO alignment in the course ‘Object Oriented Programming’ based on current CLO definitions.",
    ],
    "Faculty Info Agent": [
        "Retrieve and summarize Dr. Ahmed Raza’s recent publications and research areas from Google Scholar.",
        "Show details of all faculty members in the Department of Computer Science, including their designation and specialization.",
        "Provide details of faculty members serving on academic committees.",
        "Display the profile and specialization areas of Dr. Sana Malik.",
        "Give me complete list of the faculty of CS department.",
        "Show faculty members that have administrative roles such as Program Coordinator or Head of Department.",
    ],
    "Degree Advisor": [
        "I have done my bachelor’s in AI and want to explore business side now for my master’s. Provide me best program for me",
        "List the requirements for BS AI",
        "List all the semester-wise courses for MS AI",
    ],
    "Timetable Agent": [
        "Generate my timetable for the following courses Computer Vision AI A, OBL AI D and Agentic AI AI A and Gen AI CS D",
        "Update my schedule after dropping the course ‘Web Engineering’ and add ‘Machine Learning’ instead.",
    ],
    "University Info Agent": [
        "What is the grading policy?",
        "What is the student code of conduct",
        "Show the disciplinary code and graduation requirements for BS Computer Science.",
    ],
}


# --- Utility Functions (Unchanged) ---
def create_evaluation_prompt(metric_prompt: str, query: str, response: str) -> str:
    """Fills the template with the specific query and response."""
    # Assuming 'Reponse' was a typo in the original prompt and fixing it to 'Response'
    return metric_prompt.replace("{{query}}", query).replace("{{response}}", response)


def evaluate_with_llm(full_prompt: str) -> Dict[str, Any]:
    """
    FIXED: Calls the LLM and attempts to parse a JSON response by explicitly
    extracting string content and stripping markdown fences.
    """
    try:
        # 1. Invoke the LLM synchronously
        response_object = llm.invoke(full_prompt)

        # 2. Extract the string content (Fix for 'AIMessage' object issue)
        # Check for common object attributes like 'content' or assume it's a string
        if hasattr(response_object, "content") and isinstance(
            response_object.content, str
        ):
            response_text = response_object.content
        elif isinstance(response_object, str):
            response_text = response_object
        else:
            return {
                "Score": None,
                "Reasoning": f"LLM invocation returned unexpected object type: {type(response_object).__name__}",
            }

        # 3. Clean the response text (remove markdown fences)
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[len("```json") :].strip()
        elif cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[len("```") :].strip()
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[: -len("```")].strip()

        # 4. Attempt to parse the JSON string
        return json.loads(cleaned_text)

    except json.JSONDecodeError as e:
        # Provide detail about the parsing failure
        return {
            "Score": None,
            "Reasoning": f"Failed to parse LLM JSON response. Error: {e}. Raw content (snippet): {response_text[:100]}...",
        }
    except Exception as e:
        return {"Score": None, "Reasoning": f"LLM invocation failed: {e}"}


# --- Agent Invocation (Unchanged) ---
async def get_supervisor_response(
    question: str, session_id: str = "cli_session", user_role: str = "student"
) -> Optional[str]:
    """
    Sends a question to the supervisor_graph and returns the final response string.
    """
    full_response = None
    try:
        initial_state = {
            "question": question,
            "session_id": session_id,
            "route": [],
            "result": "",
            "conversation_history": [],
            "user_role": user_role,
        }
        final_state: Dict[str, Any] = await supervisor_graph.ainvoke(initial_state)
        full_response = final_state.get("result")
    except Exception as e:
        return f"An internal error occurred while processing your request: {e}"
    return full_response


# --- Main Logic (Completed) ---
async def main():
    SESSIONID = "test_session"
    USERROLE = "student"
    OUTPUT_FILE = Path("evaluation_results.json")

    # 1. Collect all agent responses
    agent_responses: List[Dict[str, str]] = []

    print("--- 1. COLLECTING AGENT RESPONSES ---")
    for agent, queries in queries_for_agents.items():
        print(f"\nEvaluating {agent} ({len(queries)} queries)...")
        for query in queries:
            response = await get_supervisor_response(
                query, session_id=SESSIONID, user_role=USERROLE
            )

            agent_responses.append(
                {
                    "agent": agent,
                    "query": query,
                    "response": response,
                }
            )
            print(f"  -> Collected response for: {query[:50]}...")

    # 2. Run LLM evaluations on collected data
    final_results: List[Dict[str, Any]] = []

    print("\n\n--- 2. RUNNING LLM EVALUATIONS ---")
    total_evals = len(agent_responses) * len(PROMPT_KEYS)
    eval_count = 0

    for item in agent_responses:
        query = item["query"]
        response = item["response"]

        for metric_name, metric_prompt in PROMPT_KEYS:
            eval_count += 1
            print(
                f"\n[{eval_count}/{total_evals}] Evaluating {metric_name} for Query: {query[:50]}..."
            )

            full_prompt = create_evaluation_prompt(metric_prompt, query, response)

            # Run the synchronous LLM call
            llm_output = evaluate_with_llm(full_prompt)
            score = llm_output.get("Score")
            reasoning = llm_output.get("Reasoning")

            # Structure the final result entry
            result_entry = {
                "agent": item["agent"],
                "query": query,
                "response": response,
                "evaluation_kind": metric_name,
                "score": float(score) if score is not None else None,
                "reasoning": reasoning,
            }
            final_results.append(result_entry)

            print(f"  -> Score: {score}, Reasoning: {reasoning[:70]}...")

    # 3. Save the results
    print("\n\n--- 3. SAVING RESULTS ---")
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(final_results, f, ensure_ascii=False, indent=4)
        print(
            f"Evaluation complete. Results saved successfully to: {OUTPUT_FILE.resolve()}"
        )
    except Exception as e:
        print(f"ERROR: Could not save results to file {OUTPUT_FILE}: {e}")


if __name__ == "__main__":
    try:
        # Run the main asynchronous function
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript terminated by user.")
    except Exception as e:
        print(f"An unexpected error occurred during execution: {e}")
