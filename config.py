import os
from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# Disable ChromaDB telemetry to prevent posthog errors
os.environ["ANONYMIZED_TELEMETRY"] = "False"

load_dotenv()

# Provider config
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "auto").strip().lower()
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
EMBEDDING_TIMEOUT_SECONDS = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "30"))
OPENAI_EMBEDDING_BATCH_SIZE = int(os.getenv("OPENAI_EMBEDDING_BATCH_SIZE", "64"))


def _resolve_llm_provider() -> str:
    if LLM_PROVIDER in {"groq", "openai"}:
        return LLM_PROVIDER
    if GROQ_API_KEY:
        return "groq"
    if OPENAI_API_KEY:
        return "openai"
    raise RuntimeError(
        "No LLM API key configured. Set GROQ_API_KEY or OPENAI_API_KEY."
    )


def _resolve_embedding_provider() -> str:
    if EMBEDDING_PROVIDER in {"ollama", "openai"}:
        return EMBEDDING_PROVIDER
    # Auto mode: prefer OpenAI embeddings when OPENAI key is present.
    # This avoids requiring local Ollama when cloud-only setup is intended.
    if OPENAI_API_KEY:
        return "openai"
    return "ollama"


_llm_provider = _resolve_llm_provider()
_embedding_provider = _resolve_embedding_provider()

# Embeddings
if _embedding_provider == "openai":
    embeddings = OpenAIEmbeddings(
        model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        api_key=OPENAI_API_KEY,
        request_timeout=EMBEDDING_TIMEOUT_SECONDS,
        max_retries=1,
        chunk_size=OPENAI_EMBEDDING_BATCH_SIZE,
    )
else:
    embeddings = OllamaEmbeddings(
        model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    )

# LLMs
if _llm_provider == "openai":
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini"),
        api_key=OPENAI_API_KEY,
        temperature=0.0,
        streaming=True,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )
    small_llm = ChatOpenAI(
        model=os.getenv("OPENAI_SMALL_MODEL", os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")),
        api_key=OPENAI_API_KEY,
        temperature=0.0,
        streaming=True,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )
else:
    llm = ChatGroq(
        model=os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-120b"),
        api_key=GROQ_API_KEY,
        temperature=0.0,
        streaming=True,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )
    small_llm = ChatGroq(
        model=os.getenv("GROQ_SMALL_MODEL", "llama-3.1-8b-instant"),
        api_key=GROQ_API_KEY,
        temperature=0.0,
        streaming=True,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )

__all__ = ["embeddings", "llm", "small_llm"]
