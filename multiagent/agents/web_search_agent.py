"""
Web search agent using DuckDuckGo search.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any

root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from langchain_community.tools import DuckDuckGoSearchRun
from langchain.agents import Tool
from config import llm


class WebSearchAgent:
    """Agent that performs web searches using DuckDuckGo."""
    
    def __init__(self):
        """Initialize the web search agent."""
        self.search_tool = DuckDuckGoSearchRun()
    
    def search(self, query: str, max_results: int = 5) -> str:
        """
        Perform a web search and return formatted results.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            
        Returns:
            Formatted search results as string
        """
        try:
            # DuckDuckGoSearchRun returns string results
            raw_results = self.search_tool.run(query)
            
            if not raw_results or raw_results.lower() == "no good duckduckgo search result was found":
                return f"No search results found for: {query}"
            
            # Format results
            formatted = f"Web search results for '{query}':\n\n{raw_results}"
            return formatted
            
        except Exception as e:
            return f"Error performing web search: {str(e)}"
    
    def answer_with_search(self, question: str) -> str:
        """
        Answer a question by searching the web and synthesizing results.
        
        Args:
            question: User's question
            
        Returns:
            Answer based on search results
        """
        try:
            # Perform search
            search_results = self.search(question)
            
            if "No search results found" in search_results or "Error" in search_results:
                return search_results
            
            # Use LLM to synthesize answer from search results
            from langchain_core.messages import HumanMessage, SystemMessage
            
            system_prompt = (
                "You are a helpful assistant that answers questions based on web search results.\n"
                "Synthesize the search results into a clear, concise answer.\n"
                "If the search results don't contain relevant information, say so.\n"
                "Always cite that your answer is based on web search results."
            )
            
            user_prompt = f"Question: {question}\n\nSearch Results:\n{search_results}\n\nPlease provide a clear answer based on these search results."
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = llm.invoke(messages)
            return response.content if hasattr(response, "content") else str(response)
            
        except Exception as e:
            return f"Error generating answer from search results: {str(e)}"
    
    def stream_answer(self, question: str):
        """
        Stream answer with search results.
        
        Args:
            question: User's question
            
        Yields:
            Answer chunks
        """
        try:
            # Perform search
            search_results = self.search(question)
            
            if "No search results found" in search_results or "Error" in search_results:
                yield search_results
                return
            
            # Stream LLM response
            from langchain_core.messages import HumanMessage, SystemMessage
            
            system_prompt = (
                "You are a helpful assistant that answers questions based on web search results.\n"
                "Synthesize the search results into a clear, concise answer.\n"
                "If the search results don't contain relevant information, say so.\n"
                "Always cite that your answer is based on web search results."
            )
            
            user_prompt = f"Question: {question}\n\nSearch Results:\n{search_results}\n\nPlease provide a clear answer based on these search results."
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            for chunk in llm.stream(messages):
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
                    
        except Exception as e:
            yield f"Error: {str(e)}"


# Convenience function
def get_web_search_agent() -> WebSearchAgent:
    """Get a web search agent instance."""
    return WebSearchAgent()


if __name__ == "__main__":
    # Test the web search agent
    agent = WebSearchAgent()
    
    test_queries = [
        "What is the latest news about AI?",
        "FAST University Islamabad location",
        "Python programming best practices"
    ]
    
    for query in test_queries:
        print(f"\n{'='*80}")
        print(f"Query: {query}")
        print(f"{'='*80}")
        
        result = agent.answer_with_search(query)
        print(result)
