import os
from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings
from langchain_groq import ChatGroq


load_dotenv()

# Embeddings
embeddings = OllamaEmbeddings(model="nomic-embed-text")

# LLM (Groq)
llm = ChatGroq(
    model="openai/gpt-oss-20b",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.1,
    streaming=True,
)

__all__ = ["embeddings", "llm"]
