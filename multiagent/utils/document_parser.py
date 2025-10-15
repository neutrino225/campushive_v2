"""
Document Parser Utility

Extracts text content from various file formats for vector store ingestion.
"""

import os
import tempfile
from typing import Optional
from pathlib import Path


def parse_document(file_content: bytes, filename: str) -> str:
    """
    Parse document content from various file formats.
    
    Args:
        file_content: Raw bytes of the file
        filename: Name of the file (used to determine type)
    
    Returns:
        Extracted text content
    
    Raises:
        ValueError: If file type is not supported
    """
    file_ext = Path(filename).suffix.lower()
    
    if file_ext == '.txt':
        return _parse_text(file_content)
    elif file_ext == '.md':
        return _parse_markdown(file_content)
    elif file_ext == '.pdf':
        return _parse_pdf(file_content)
    elif file_ext in ['.doc', '.docx']:
        return _parse_docx(file_content)
    else:
        raise ValueError(f"Unsupported file type: {file_ext}")


def _parse_text(file_content: bytes) -> str:
    """Parse plain text file."""
    try:
        return file_content.decode('utf-8')
    except UnicodeDecodeError:
        # Try with different encoding
        return file_content.decode('latin-1')


def _parse_markdown(file_content: bytes) -> str:
    """Parse markdown file (same as text)."""
    return _parse_text(file_content)


def _parse_pdf(file_content: bytes) -> str:
    """Parse PDF file using PyPDF2 or pdfplumber."""
    try:
        import PyPDF2
        import io
        
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text_parts = []
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    except ImportError:
        raise ValueError("PyPDF2 is required for PDF parsing. Install with: pip install PyPDF2")
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}")


def _parse_docx(file_content: bytes) -> str:
    """Parse DOCX file using python-docx."""
    try:
        import docx
        import io
        
        doc_file = io.BytesIO(file_content)
        doc = docx.Document(doc_file)
        
        text_parts = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_parts.append(paragraph.text)
        
        return "\n\n".join(text_parts)
    
    except ImportError:
        raise ValueError("python-docx is required for DOCX parsing. Install with: pip install python-docx")
    except Exception as e:
        raise ValueError(f"Failed to parse DOCX: {str(e)}")


def get_supported_extensions() -> list[str]:
    """Return list of supported file extensions."""
    return ['.txt', '.md', '.pdf', '.doc', '.docx']


def is_supported_file(filename: str) -> bool:
    """Check if file type is supported."""
    return Path(filename).suffix.lower() in get_supported_extensions()
