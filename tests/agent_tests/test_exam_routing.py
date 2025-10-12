import asyncio
import json
import os
import pytest

from multiagent.graph.supervisor import run_supervisor_async
from vector_store_manager import VectorStoreManager, VectorStoreType
from config import embeddings

@pytest.mark.asyncio
async def test_supervisor_routes_to_exam(tmp_path):
    # Make sure EXAMS store can build with minimal data
    data_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(data_dir, exist_ok=True)
    structured_path = os.path.join(data_dir, "structured_exams.json")
    payload = [
        {
            "course": "OOP",
            "exam_type": "Final",
            "filename": "dummy.pdf",
            "questions": [
                {"question_text": "Explain inheritance.", "marks": 5, "difficulty": "Easy", "topic": "Inheritance"}
            ]
        }
    ]
    with open(structured_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    VectorStoreManager(embeddings=embeddings).create_vector_store(VectorStoreType.EXAMS, force_recreate=True)

    result = await run_supervisor_async(
        "Generate a final exam for OOP with 3 questions, worth 30 marks.",
        session_id="test_exam_route",
        user_role="faculty",
    )
    assert result and isinstance(result.get("response"), str)
    assert any("exam" in (step.lower()) for step in result.get("route", []))
