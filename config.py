import os
from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings
from langchain_groq import ChatGroq

# Disable ChromaDB telemetry to prevent posthog errors
os.environ["ANONYMIZED_TELEMETRY"] = "False"

load_dotenv()

# Embeddings
embeddings = OllamaEmbeddings(model="nomic-embed-text")

# LLM (Groq)
llm = ChatGroq(
    model="openai/gpt-oss-120b",  # Better at following strict instructions
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.0, 
    streaming=True,
)


small_llm = ChatGroq(
    model="llama-3.1-8b-instant",  # Faster, cheaper, but less capable
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.0,   
    streaming=True,
)

__all__ = ["embeddings", "llm", "small_llm"]
