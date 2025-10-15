"""
Session-Specific Vector Store Retriever Manager

Manages dynamic, per-session vector stores for uploaded documents.
"""

import os
from typing import Optional
from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter


class SessionRetrieverManager:
    """Manages session-specific vector stores for uploaded documents."""
    
    def __init__(self, embeddings, base_path: str = "data/vector_stores/user_uploads"):
        """
        Initialize the session retriever manager.
        
        Args:
            embeddings: Embedding model to use for vectorization
            base_path: Base directory for session vector stores
        """
        self.embeddings = embeddings
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)
    
    def get_session_store_path(self, user_id: int, session_id: str) -> str:
        """Get the path for a session's vector store."""
        return os.path.join(self.base_path, f"user_{user_id}_session_{session_id}")
    
    def get_session_retriever(self, user_id: int, session_id: str, search_kwargs: dict = None) -> Optional[VectorStoreRetriever]:
        """
        Get a retriever for a session's vector store.
        
        Args:
            user_id: User ID
            session_id: Session ID
            search_kwargs: Optional search parameters (e.g., {"k": 5})
        
        Returns:
            VectorStoreRetriever if store exists, None otherwise
        """
        store_path = self.get_session_store_path(user_id, session_id)
        
        if not os.path.exists(store_path):
            return None
        
        try:
            vector_store = Chroma(
                persist_directory=store_path,
                embedding_function=self.embeddings
            )
            
            # Check if store has documents
            if vector_store._collection.count() == 0:
                return None
            
            search_kwargs = search_kwargs or {"k": 5}
            return vector_store.as_retriever(search_kwargs=search_kwargs)
        
        except Exception as e:
            print(f"Error loading session retriever: {e}")
            return None
    
    def has_documents(self, user_id: int, session_id: str) -> bool:
        """Check if a session has uploaded documents."""
        retriever = self.get_session_retriever(user_id, session_id)
        return retriever is not None
    
    def ingest_document(self, user_id: int, session_id: str, text_content: str, filename: str) -> dict:
        """
        Ingest a document into the session's vector store.
        
        Args:
            user_id: User ID
            session_id: Session ID
            text_content: Extracted text from document
            filename: Original filename
        
        Returns:
            Dictionary with ingestion statistics
        """
        store_path = self.get_session_store_path(user_id, session_id)
        
        # Split text into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        
        chunks = text_splitter.split_text(text_content)
        
        # Add metadata to each chunk
        metadatas = [{"source": filename, "chunk": i} for i in range(len(chunks))]
        
        # Create or load vector store
        if os.path.exists(store_path):
            # Add to existing store
            vector_store = Chroma(
                persist_directory=store_path,
                embedding_function=self.embeddings
            )
            vector_store.add_texts(chunks, metadatas=metadatas)
        else:
            # Create new store
            vector_store = Chroma.from_texts(
                texts=chunks,
                embedding=self.embeddings,
                metadatas=metadatas,
                persist_directory=store_path
            )
        
        return {
            "chunks_created": len(chunks),
            "filename": filename,
            "store_path": store_path
        }
    
    def delete_session_store(self, user_id: int, session_id: str) -> bool:
        """
        Delete a session's vector store.
        
        Args:
            user_id: User ID
            session_id: Session ID
        
        Returns:
            True if deleted, False if didn't exist
        """
        import shutil
        
        store_path = self.get_session_store_path(user_id, session_id)
        
        if os.path.exists(store_path):
            shutil.rmtree(store_path)
            return True
        
        return False


# Global instance
_session_retriever_manager = None


def get_session_retriever_manager(embeddings=None):
    """Get the global session retriever manager instance."""
    global _session_retriever_manager
    
    if _session_retriever_manager is None:
        if embeddings is None:
            from config import embeddings as default_embeddings
            embeddings = default_embeddings
        _session_retriever_manager = SessionRetrieverManager(embeddings)
    
    return _session_retriever_manager


def get_session_retriever(user_id: int, session_id: str, search_kwargs: dict = None) -> Optional[VectorStoreRetriever]:
    """
    Convenience function to get a session retriever.
    
    Args:
        user_id: User ID
        session_id: Session ID (can be string or int)
        search_kwargs: Optional search parameters
    
    Returns:
        VectorStoreRetriever if documents exist, None otherwise
    """
    # Convert session_id to string
    if isinstance(session_id, int):
        session_id = str(session_id)
    
    manager = get_session_retriever_manager()
    return manager.get_session_retriever(user_id, session_id, search_kwargs)


def has_session_documents(user_id: int, session_id: str) -> bool:
    """Check if a session has uploaded documents."""
    if isinstance(session_id, int):
        session_id = str(session_id)
    
    manager = get_session_retriever_manager()
    return manager.has_documents(user_id, session_id)
