import os
import sys
from pathlib import Path

# Add the root directory to the Python path so we can import from root modules
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from langchain.prompts import PromptTemplate
from langchain_core.messages import HumanMessage
from langchain_community.tools import DuckDuckGoSearchResults
from utils import normalize_university_query
from vector_store_manager import VectorStoreManager, VectorStoreType
from config import embeddings, llm

class RAGEngine:
    """Reusable RAG engine with pluggable retriever and prompt.

    Minimal contract:
    - Inputs: question (str)
    - Uses: retriever.invoke(question) -> list[Document]
    - Prompt: a PromptTemplate with variables ["context", "question"]
    - Output: final string answer (also streamed to stdout if stream=True)
    """

    def __init__(
        self,
        llm,
        retriever,
        prompt: PromptTemplate,
        normalize_fn=None,
        debug: bool = False,
    ):
        if retriever is None:
            raise ValueError("RAGEngine requires a retriever")
        if prompt is None:
            raise ValueError("RAGEngine requires a prompt template")
        self.llm = llm
        self.retriever = retriever
        self.prompt = prompt
        self.normalize_fn = normalize_fn
        self.debug = debug

    # --- Generic ensemble construction helpers ---
    @staticmethod
    def build_ensemble_retriever(
        split_docs,
        vector_store,
        *,
        bm25_k: int = 15,
        embed_k: int = 15,
        mmr_k: int = 15,
        mmr_fetch_k: int = 30,
        mmr_lambda: float = 0.5,
        weights = (0.5, 0.3, 0.2),
    ) -> EnsembleRetriever:
        """Build a hybrid EnsembleRetriever over BM25 + vector similarity + MMR.

        Returns an EnsembleRetriever ready to be used by RAGEngine.
        """
        bm25 = BM25Retriever.from_documents(split_docs)
        bm25.k = bm25_k

        embedding_retriever = vector_store.as_retriever(
            search_type="similarity", search_kwargs={"k": embed_k}
        )

        mmr_retriever = vector_store.as_retriever(
            search_type="mmr",
            search_kwargs={"k": mmr_k, "fetch_k": mmr_fetch_k, "lambda_mult": mmr_lambda},
        )

        return EnsembleRetriever(
            retrievers=[bm25, embedding_retriever, mmr_retriever],
            weights=list(weights),
        )

    @classmethod
    def from_vector_store_manager(
        cls,
        *,
        llm,
        store_type: VectorStoreType,
        prompt: PromptTemplate,
        normalize_fn=None,
        debug: bool = False,
        use_ensemble: bool = True,
    ) -> "RAGEngine":
        """Factory: create a RAGEngine using the centralized vector store manager.
        
        This is the new preferred way to create RAG engines.
        """
        manager = VectorStoreManager(embeddings=embeddings)
        retriever = manager.get_retriever(store_type, use_ensemble=use_ensemble)

        return cls(
            llm=llm,
            retriever=retriever,
            prompt=prompt,
            normalize_fn=normalize_fn,
            debug=debug,
        )

    def retrieve(self, question: str):
        q = question.strip()
        if self.normalize_fn:
            q = self.normalize_fn(q)
        return self.retriever.invoke(q)

    def _build_context(self, docs):
        return "\n".join(doc.page_content for doc in docs)

    # --- Deterministic extractors for brittle FAQs (avoids LLM guessing) ---
    @staticmethod
    def _extract_rector_from_text(text: str) -> str | None:
        """Try to extract the Rector's name deterministically from markdown-like text.

        Heuristics:
        - Look for a bold/heading 'Rector' line followed by a name on the next line.
        - Look for inline patterns like 'Rector NUCES, Dr. X Y' or 'Rector: Dr. X Y'.
        - Return the majority/most frequent candidate if multiple are found; else the first.
        """
        import re
        if not text:
            return None

        candidates: list[str] = []

        # Pattern 1: '**Rector**\nName' or 'Rector\nName'
        for m in re.finditer(r"(?mi)^(?:\*\*?)?\s*rector\s*(?:\*\*?)?\s*$\s*^\s*([^\n]+)$", text):
            line = m.group(1).strip()
            # Basic name cleanup
            line = re.sub(r"^(?:Dr\.|Prof(?:essor)?)\s*", "Dr. ", line, flags=re.IGNORECASE)
            candidates.append(line)

        # Pattern 2: 'Rector (NUCES)?, Dr. X Y' inline
        for m in re.finditer(r"(?i)rector(?:\s+nuces)?\s*(?:,|:)?\s*(dr\.|prof(?:essor)?)\s+([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,3})", text):
            title = m.group(1)
            name = m.group(2).strip()
            title_norm = "Dr." if title.lower().startswith("dr") else "Prof."
            candidates.append(f"{title_norm} {name}")

        if not candidates:
            return None

        # Normalize whitespace
        candidates = [re.sub(r"\s+", " ", c).strip(" ,") for c in candidates if c.strip()]

        # Majority vote: pick most frequent
        from collections import Counter
        counts = Counter(candidates)
        best, _ = counts.most_common(1)[0]
        return best

    def _try_fact_answers(self, question: str, docs) -> str | None:
        """Short-circuit certain FAQs with deterministic parsing from retrieved docs."""
        q = (question or "").lower()
        if any(kw in q for kw in [" who is the rector", " rector of", "who is rector", "who's the rector", "who is the vice chancellor", "vice-chancellor"]):
            # 1) Canonical facts file (if present)
            try:
                from pathlib import Path
                import json as _json
                facts_path = Path(__file__).parent.parent.parent / "data" / "general" / "current_facts.json"
                if facts_path.exists():
                    data = _json.loads(facts_path.read_text(encoding="utf-8"))
                    name = (data.get("rector_name") or "").strip()
                    if name:
                        return name
            except Exception:
                pass
            # 2) Parse from retrieved context
            joined = "\n\n".join(doc.page_content for doc in (docs[:5] if isinstance(docs, list) else []))
            name = self._extract_rector_from_text(joined)
            if name:
                return name
            # If not confidently extracted, fall back to LLM flow
        return None

    def _stream_llm(self, prompt_text: str) -> str:
        try:
            stream = self.llm.stream([HumanMessage(content=prompt_text)])
            full = ""
            for chunk in stream:
                if hasattr(chunk, "content") and chunk.content:
                    print(chunk.content, end="", flush=True)
                    full += chunk.content
            print("\n")
            return full
        except Exception as e:
            print(f"Error generating response: {e}")
            return "Error generating response"

    def answer(self, question: str, stream: bool = True) -> str:
        if not question or not question.strip():
            return ""
        docs = self.retrieve(question)
        # Deterministic short-circuit for certain FAQs (e.g., rector)
        try:
            fact = self._try_fact_answers(question, docs)
            if fact:
                return fact
        except Exception:
            # Never break answering due to extractor issues
            pass
        context = self._build_context(docs)
        prompt_text = self.prompt.format(context=context, question=question)
        if stream:
            return self._stream_llm(prompt_text)
        try:
            resp = self.llm.invoke([HumanMessage(content=prompt_text)])
            return resp.content if hasattr(resp, "content") else str(resp)
        except Exception as e:
            return f"Error generating response: {e}"

    def stream_answer(self, question: str):
        """Stream the answer in chunks."""
        if not question or not question.strip():
            return
        docs = self.retrieve(question)
        # Deterministic short-circuit for certain FAQs
        try:
            fact = self._try_fact_answers(question, docs)
            if fact:
                # Stream the fact as a single chunk
                yield fact
                return
        except Exception:
            pass
        context = self._build_context(docs)
        prompt_text = self.prompt.format(context=context, question=question)
        try:
            stream = self.llm.stream([HumanMessage(content=prompt_text)])
            for chunk in stream:
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
        except Exception as e:
            yield f"Error generating response: {e}"


class AdvancedUniversityRAGCLI:
    """Advanced Interactive CLI for University Knowledge Base RAG System (no automatic fallbacks)."""
    
    def __init__(self, debug_mode=False):
        self.debug_mode = debug_mode
        self.retriever = None
        self.prompt_template = None
        self.online_prompt_template = None
        self.search = DuckDuckGoSearchResults(output_format="list")
        self.min_context_threshold = 100  # Minimum context length to consider as "found"
        self.mode = "local"  # 'local' or 'online'
        self.setup_system()

    def setup_system(self):
        """Initialize the RAG system components."""
        if self.debug_mode:
            print("Initializing University Knowledge Base...")
        persist_dir = "./chroma_db"

        # Common prompt for local answers
        local_prompt = PromptTemplate(
            input_variables=["context", "question"],
            template=(
                "You are an assistant for FAST-NUCES Islamabad university knowledge base.\n\n"
                "CRITICAL RULES:\n"
                "1. Answer ONLY using information explicitly stated in the context below\n"
                "2. Do NOT add details, steps, or information from your training data\n"
                "3. Do NOT make up URLs, procedures, or requirements\n"
                "4. When the context contains step-by-step procedures, include ALL steps\n"
                "5. When the context has detailed information, provide complete details\n"
                "6. If the answer is not explicitly stated in the context, reply exactly: NOT_FOUND_IN_DOCUMENTS\n\n"
                "Context:\n{context}\n\n"
                "Question: {question}\n\n"
                "Answer (provide complete information from the context):"
            ),
        )

        # Use the centralized vector store manager for general university information
        try:
            if self.debug_mode:
                print("Using centralized vector store manager for general university information")
            self.engine = RAGEngine.from_vector_store_manager(
                llm=llm,
                store_type=VectorStoreType.GENERAL,
                prompt=local_prompt,
                normalize_fn=normalize_university_query,
                debug=self.debug_mode,
                use_ensemble=True,
            )
        except Exception as e:
            print(f"Error setting up vector store manager: {e}")
            print("Cannot initialize local RAG engine. Please ensure the vector store is properly configured.")
            print("Run the admin scripts to initialize the vector stores.")
            self.engine = None
            return

        # Keep a direct handle for the CLI
        self.retriever = self.engine.retriever

        # Prompt templates (reuse the same as engine for local; keep separate var for clarity)
        self.prompt_template = self.engine.prompt

        self.online_prompt_template = PromptTemplate(
            input_variables=["context", "question"],
            template=(
                "You are an assistant for a university knowledge base. "
                "The following information was found from online sources (isb.nu.edu.pk or nu.edu.pk). "
                "Answer the question using this online context. "
                "Be clear that this information comes from online university sources.\n\n"
                "Online Context:\n{context}\n\nQuestion: {question}\nAnswer:"
            ),
        )
        
        # Check SearxNG availability
        if self.debug_mode:
            print("DuckDuckGo search available")
            print("Advanced RAG system ready! Type your questions or 'help' for commands.\n")
    
    def print_debug_context(self, docs, query):
        """Pretty print debug information about retrieved context."""
        print(f"\n{'='*60}")
        print(f"DEBUG MODE - Query Analysis")
        print(f"{'='*60}")
        print(f"Original Query: {query}")
        
        normalized = normalize_university_query(query)
        if normalized != query:
            print(f"Normalized to: {normalized}")
        
        print(f"\nRetrieved {len(docs)} documents:")
        print("-" * 40)
        
        for i, doc in enumerate(docs[:5], 1):  # Show top 5
            src = os.path.basename(doc.metadata.get("source", "unknown"))
            content = doc.page_content[:200].replace("\n", " ").strip()
            score = doc.metadata.get("score") or doc.metadata.get("relevance_score")
            suffix = f" (score: {score:.3f})" if isinstance(score, (int, float)) else ""

            print(f"[{i}] {src}{suffix}")
            print(f"    Content: {content}...")
            print()
        
        print(f"{'='*60}\n")
    
    def stream_response(self, prompt):
        """Generate and stream the response."""
        try:
            # Get streaming response
            response = llm.stream([HumanMessage(content=prompt)])
            full_response = ""
            
            for chunk in response:
                if hasattr(chunk, 'content') and chunk.content:
                    print(chunk.content, end="", flush=True)
                    full_response += chunk.content
            
            print("\n")  # New line after streaming
            return full_response
            
        except Exception as e:
            print(f"Error generating response: {e}")
            return "Sorry, I encountered an error while generating the response."
    
    def answer_question(self, query):
        """Process a user question using the selected mode only (no fallbacks)."""
        if not query.strip():
            return
        
        try:
            # Apply query normalization
            normalized_query = normalize_university_query(query)
            if self.mode == "local":
                return self._answer_local(query, normalized_query)
            else:
                return self._answer_online(query)
            
        except Exception as e:
            print(f"Error processing question: {e}")

    def _answer_local(self, user_query: str, normalized_query: str):
        if self.retriever is None:
            print("Local knowledge base is not available. Please ensure the vector store is properly configured.")
            return
            
        if self.debug_mode:
            print("Searching local knowledge base...")
        docs = self.retriever.invoke(normalized_query)
        context = "\n".join([doc.page_content for doc in docs])

        if self.debug_mode:
            self.print_debug_context(docs, user_query)

        if len(context.strip()) < self.min_context_threshold:
            if self.debug_mode:
                print("No sufficient context found in local documents.")
            return

        final_prompt = self.prompt_template.format(context=context, question=user_query)
        response = self._get_complete_response(final_prompt)

        if not response or "NOT_FOUND_IN_DOCUMENTS" in response:
            if self.debug_mode:
                print("Not found in local documents.")
            return

        self._stream_text(response)
        if self.debug_mode:
            self._print_local_sources(docs)

    def _answer_online(self, user_query: str):
        try:
            online_results = self.search.invoke(user_query)
            filtered_results = [
                result for result in online_results
                if any(domain in result.get('link', '') for domain in ['isb.nu.edu.pk', 'nu.edu.pk'])
            ][:5]

            if not filtered_results:
                if self.debug_mode:
                    print("No relevant information found on university sites (isb.nu.edu.pk, nu.edu.pk).")
                return

            online_context = ""
            for result in filtered_results:
                online_context += f"Title: {result['title']}\n"
                online_context += f"URL: {result['link']}\n"
                online_context += f"Content: {result['snippet']}\n\n"

            if self.debug_mode:
                self._print_online_debug_context(filtered_results, user_query)

            final_prompt = self.online_prompt_template.format(context=online_context, question=user_query)
            self.stream_response(final_prompt)

            if self.debug_mode:
                print(f"\nSources:")
                for result in filtered_results:
                    print(f"   • {result['title']} - {result['link']}")
        except Exception as e:
            print(f"Error during online search: {e}")
    
    # Fallback method removed to enforce explicit modes only
    
    def _get_complete_response(self, prompt):
        """Get complete response without streaming for evaluation."""
        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            print(f"Error generating response: {e}")
            return "Error generating response"
    
    def _stream_text(self, text):
        """Stream pre-generated text character by character."""
        import time
        for char in text:
            print(char, end="", flush=True)
            time.sleep(0.01)  # Small delay for streaming effect
        print("\n")
    
    def _print_online_debug_context(self, results, query):
        """Print debug information for online search results."""
        print(f"\n{'='*60}")
        print(f"DUCKDUCKGO SEARCH DEBUG - Query Analysis")
        print(f"{'='*60}")
        print(f"Query: {query}")
        print(f"Found {len(results)} online results:")
        print("-" * 40)
        
        for i, result in enumerate(results, 1):
            print(f"[{i}] {result['title']}")
            print(f"    URL: {result['link']}")
            print(f"    Content: {result['snippet'][:150]}...")
            print()
        
        print(f"{'='*60}\n")

    def _print_local_sources(self, docs):
        """Print unique local document sources used for the answer."""
        try:
            unique = []
            seen = set()
            for d in docs:
                src = d.metadata.get("source") or "unknown"
                base = os.path.basename(src)
                if base not in seen:
                    unique.append(base)
                    seen.add(base)
            if unique:
                print("Sources (local):")
                for s in unique[:10]:  # limit to top 10
                    print(f"   • {s}")
        except Exception:
            # Don't fail the main flow if metadata is missing
            pass
    
    def show_help(self):
        """Display help information."""
        print(f"""
{'='*60}
Advanced University Knowledge Base - Help
{'='*60}

Available Commands:
  help          - Show this help message
  debug on/off  - Toggle debug mode (shows retrieval context)
  clear         - Clear the screen
    mode local    - Use only local knowledge base
    mode online   - Use only DuckDuckGo results (nu.edu.pk, isb.nu.edu.pk)
  exit/quit     - Exit the application

Usage:
  • Ask questions about the university in natural language
  • Examples:
    - "Who is the rector?"
    - "What is the registrar's email?" 
    - "List the deans of different faculties"
    - "Who heads the Computer Science department?"
    - "What are the admission requirements?"

Advanced Features:
  • Auto-normalizes university name variations (FAST-NUCES → full name)
  • Intelligent retrieval using hybrid BM25 + semantic search
    • Online search using DuckDuckGo (isb.nu.edu.pk, nu.edu.pk only)
  • Streaming responses for better user experience
  • Debug mode shows retrieved document context
  • Source attribution for online results

How it works:
    • In 'local' mode, answers strictly from local documents (no online).
    • In 'online' mode, answers strictly from university websites via DuckDuckGo.

Debug Mode: {'ON' if self.debug_mode else 'OFF'}
DuckDuckGo Status: Available
Mode: {self.mode.upper()}
{'='*60}
        """)
    
    def run(self):
        """Main CLI loop."""
        searxng_status = "DuckDuckGo Search Available"
        print(f"""
{'='*60}
Welcome to Advanced University Knowledge Base
{'='*60}
Ask questions about university information, staff, policies, and more!
Modes: Local Only or Online Only (isb.nu.edu.pk, nu.edu.pk)

Status: {searxng_status} | Mode: {self.mode.upper()}
Type 'help' for available commands or 'exit' to quit.
{'='*60}
        """)
        
        while True:
            try:
                user_input = input("\nYou: ").strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.lower() in ['exit', 'quit', 'q']:
                    print("Thank you for using University Knowledge Base. Goodbye!")
                    break
                elif user_input.lower() == 'help':
                    self.show_help()
                elif user_input.lower() == 'clear':
                    os.system('clear' if os.name == 'posix' else 'cls')
                elif user_input.lower().startswith('mode'):
                    parts = user_input.lower().split()
                    if len(parts) > 1 and parts[1] in ['local', 'online']:
                        self.mode = parts[1]
                        print(f"Mode set to: {self.mode.upper()}")
                    else:
                        print(f"Current mode: {self.mode.upper()} (use 'mode local' or 'mode online')")
                elif user_input.lower().startswith('debug'):
                    parts = user_input.lower().split()
                    if len(parts) > 1:
                        if parts[1] in ['on', 'true', '1']:
                            self.debug_mode = True
                            print("Debug mode: ON")
                        elif parts[1] in ['off', 'false', '0']:
                            self.debug_mode = False
                            print("Debug mode: OFF")
                    else:
                        status = "ON" if self.debug_mode else "OFF"
                        print(f"Debug mode is currently: {status}")
                else:
                    # Process as a question
                    self.answer_question(user_input)
                    
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except EOFError:
                print("\n\nGoodbye!")
                break


def main(debug=False):
    """Main function - launches the interactive CLI."""
    cli = AdvancedUniversityRAGCLI(debug_mode=debug)
    cli.run()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Advanced University Knowledge Base RAG System with DuckDuckGo Search")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()
    
    main(debug=args.debug)
