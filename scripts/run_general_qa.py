from __future__ import annotations

import sys
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import llm, embeddings
from vector_store_manager import get_vector_store_manager, VectorStoreType
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="Query to ask the assistant")
    parser.add_argument(
        "--k", type=int, default=5, help="Number of documents to retrieve"
    )
    args = parser.parse_args()

    manager = get_vector_store_manager(embeddings=embeddings)

    # Ensure store exists (creates if not)
    retriever = manager.get_retriever(VectorStoreType.GENERAL, use_ensemble=True)
    # Adjust retriever kwargs if supported
    try:
        retriever.search_kwargs = {"k": args.k}
    except Exception:
        pass

    # Build a simple prompt so LLM sees context clearly
    prompt = PromptTemplate(
        input_variables=["context", "question"],
        template="""
You are an assistant that answers questions using the provided context.

Context:
{context}

Question: {question}

Answer concisely and cite context where appropriate.
""",
    )

    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        chain_type_kwargs={"prompt": prompt},
    )

    # Before running the chain, fetch raw documents for debugging
    print("Retrieving documents for debugging (k={})...".format(args.k))
    docs = retriever.get_relevant_documents(args.query)
    print(f"Retrieved {len(docs)} documents/chunks:\n")
    for i, d in enumerate(docs, 1):
        src = (
            d.metadata.get("source")
            if getattr(d, "metadata", None) is not None
            else "<no-meta>"
        )
        print(f"--- DOC {i} (source={src}) ---")
        print(d.page_content[:1000])
        print("\n")

    print("Running RetrievalQA chain to get final answer...\n")
    res = qa.run(args.query)
    print("Answer:\n")
    print(res)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
