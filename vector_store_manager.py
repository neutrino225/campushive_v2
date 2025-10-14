import os
import json
import shutil
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever

# Configure logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


class VectorStoreType(Enum):
    """Types of vector stores supported by the system."""
    DEGREE_PROGRAMS = "degree_programs"
    FACULTY = "faculty"
    GENERAL = "general"
    EXAMS = "exams"


@dataclass
class VectorStoreConfig:
    """Configuration for a specific vector store."""
    store_type: VectorStoreType
    persist_dir: str
    data_source: str  # Path to data source (JSON file or directory)
    chunk_size: int = 1000
    chunk_overlap: int = 200
    # Retriever configuration
    bm25_k: int = 15
    embed_k: int = 15
    mmr_k: int = 15
    mmr_fetch_k: int = 30
    mmr_lambda: float = 0.5
    ensemble_weights: Tuple[float, ...] = (0.5, 0.3, 0.2)


class DataProcessor:
    """Base class for processing different types of data sources."""
    
    @staticmethod
    def process_data(source_path: str) -> List[Document]:
        """Process data source and return LangChain documents."""
        raise NotImplementedError
    
    @staticmethod
    def validate_source(source_path: str) -> bool:
        """Validate that the data source exists and is readable."""
        return os.path.exists(source_path)


class DegreeDataProcessor(DataProcessor):
    """Processor for degree programs JSON data."""
    
    @staticmethod
    def process_data(source_path: str) -> List[Document]:
        """Process degree programs JSON file into documents."""
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Degree programs file not found: {source_path}")
        
        with open(source_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        documents = []
        for item in data:
            try:
                # Extract degree program information
                title = item.get("title", "")
                level = DegreeDataProcessor._extract_level(title)
                field = DegreeDataProcessor._extract_field(title)
                
                # Build document content
                content_parts = [
                    f"# {title}",
                    f"Level: {level}",
                    f"Field: {field}",
                    "",
                    "## Eligibility",
                    item.get("eligibility", ""),
                    "",
                    "## Vision",
                    item.get("vision", ""),
                    "",
                    "## Mission", 
                    item.get("mission", ""),
                    "",
                    "## Career Opportunities",
                    item.get("career_opportunities", ""),
                    ""
                ]
                
                # Add PEOs
                peos = item.get("peos", [])
                if peos:
                    content_parts.append("## Program Educational Objectives (PEOs)")
                    for i, peo in enumerate(peos, 1):
                        content_parts.append(f"{i}. {peo}")
                    content_parts.append("")
                
                # Add PLOs
                plos = item.get("plos", [])
                if plos:
                    content_parts.append("## Program Learning Outcomes (PLOs)")
                    for i, plo in enumerate(plos, 1):
                        content_parts.append(f"{i}. {plo}")
                    content_parts.append("")
                
                # Add curriculum overview
                semesters = item.get("semesters", {})
                if semesters:
                    content_parts.append("## Curriculum Overview")
                    total_credits = DegreeDataProcessor._calculate_total_credits(semesters)
                    content_parts.append(f"Total Credit Hours: {total_credits}")
                    content_parts.append(f"Duration: {len(semesters)} semesters")
                    content_parts.append("")
                
                page_content = "\n".join(content_parts)
                
                metadata = {
                    "source": f"degree_program:{title}",
                    "title": title,
                    "level": level,
                    "field": field,
                    "total_credit_hours": DegreeDataProcessor._calculate_total_credits(semesters),
                    "duration_years": max(1, len(semesters) // 2) if semesters else 4
                }
                
                documents.append(Document(page_content=page_content, metadata=metadata))
                
            except Exception as e:
                # logger.warning(f"Error processing degree program {item.get('title', 'Unknown')}: {e}")
                continue
        
        return documents
    
    @staticmethod
    def _extract_level(title: str) -> str:
        """Extract degree level from title."""
        title_lower = title.lower()
        if "bachelor" in title_lower or "bs " in title_lower or "bba" in title_lower:
            return "Bachelor"
        elif "master" in title_lower or "ms " in title_lower or "mba" in title_lower:
            return "Master"
        elif "phd" in title_lower or "doctorate" in title_lower:
            return "PhD"
        return "Unknown"
    
    @staticmethod
    def _extract_field(title: str) -> str:
        """Extract main field of study from title."""
        import re
        # Remove common prefixes and parentheses
        field = re.sub(r'^(Bachelor|Master|PhD|Doctor|MS|BS|BBA|MBA)\s*(of\s*)?', '', title, flags=re.IGNORECASE)
        field = re.sub(r'^\((.*?)\)$', r'\1', field.strip())
        field = re.sub(r'^Science\s*\((.*?)\)$', r'\1', field, flags=re.IGNORECASE)
        return field.strip()
    
    @staticmethod
    def _calculate_total_credits(semesters: Dict[str, List[Dict]]) -> int:
        """Calculate total credit hours from semester data."""
        total = 0
        for semester_courses in semesters.values():
            for course in semester_courses:
                try:
                    credits = course.get("credit_hours", 0)
                    if isinstance(credits, (int, float)):
                        total += credits
                    elif isinstance(credits, str):
                        # Try to extract number from string
                        import re
                        match = re.search(r'(\d+)', credits)
                        if match:
                            total += int(match.group(1))
                except:
                    continue
        return total


class ExamDataProcessor(DataProcessor):
    """Processor for structured exam JSON data."""

    @staticmethod
    def process_data(source_path: str) -> List[Document]:
        """Process structured exams JSON file into documents."""
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Structured exams file not found: {source_path}")

        with open(source_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        documents = []
        # Iterate over exams and questions
        for exam in data:
            course = exam.get("course", "Unknown")
            exam_type = exam.get("exam_type", "Unknown")
            questions = exam.get("questions", []) or []
            for question in questions:
                content = f"Course: {course}\nExam Type: {exam_type}\n"
                content += f"Topic: {question.get('topic', 'N/A')}\n"
                content += f"Question: {question.get('question_text', '')}\n"
                content += f"Marks: {question.get('marks', 'N/A')}"

                metadata = {
                    "source": f"exam:{course}:{exam.get('filename', '')}",
                    "course": course,
                    "exam_type": exam_type,
                    "topic": question.get("topic"),
                    "difficulty": question.get("difficulty"),
                    "marks": question.get("marks"),
                }
                documents.append(Document(page_content=content, metadata=metadata))

        return documents


class FacultyDataProcessor(DataProcessor):
    """Processor for faculty JSON data."""
    
    @staticmethod
    def process_data(source_path: str) -> List[Document]:
        """Process faculty directory with JSON files into documents."""
        if not os.path.isdir(source_path):
            raise FileNotFoundError(f"Faculty data directory not found: {source_path}")
        
        # Load all faculty JSON files
        people = []
        file_list = [f for f in os.listdir(source_path) if f.endswith('.json')]
        for fname in file_list:
            fpath = os.path.join(source_path, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    arr = json.load(f)
                    if isinstance(arr, list):
                        # Add dept from filename if missing
                        dept_code = os.path.splitext(fname)[0].upper()
                        for obj in arr:
                            if not obj.get("Department") and not obj.get("Dept_ID"):
                                obj["Department"] = dept_code
                        people.extend(arr)
            except Exception as e:
                # logger.warning(f"Error loading faculty file {fname}: {e}")
                continue
        
        # Convert to documents (show progress)
        documents = []
        for person in people:
            try:
                doc = FacultyDataProcessor._create_faculty_document(person)
                documents.append(doc)
            except Exception as e:
                # logger.warning(f"Error processing faculty member {person.get('Name', 'Unknown')}: {e}")
                continue
        
        return documents
    
    @staticmethod
    def _create_faculty_document(person: Dict[str, Any]) -> Document:
        """Create a document from faculty person data."""
        import re
        
        def strip_html(text: Optional[str]) -> str:
            if not text:
                return ""
            text = re.sub(r"\s+", " ", text)
            text = re.sub(r"<[^>]+>", " ", text)
            return re.sub(r"\s+", " ", text).strip()
        
        def norm_whitespace(s: str) -> str:
            return re.sub(r"\s+", " ", s or "").strip()
        
        def format_list_field(items: Any) -> List[str]:
            lines = []
            if not items:
                return lines
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        # Convert dict to string representation
                        line_parts = []
                        for k, v in it.items():
                            if v:
                                line_parts.append(f"{k}: {strip_html(str(v))}")
                        if line_parts:
                            lines.append(", ".join(line_parts))
                    else:
                        lines.append(norm_whitespace(strip_html(str(it))))
            else:
                lines.append(norm_whitespace(strip_html(str(items))))
            return lines
        
        # Extract and clean data
        title = norm_whitespace(str(person.get("Title") or ""))
        name = norm_whitespace(str(person.get("Name") or ""))
        display_name = f"{title} {name}".strip() if title and not name.lower().startswith(title.lower()) else name
        
        summary = strip_html(person.get("summary") or "")
        dept = norm_whitespace(str(person.get("Department") or person.get("Dept_ID") or ""))
        email = norm_whitespace(str(person.get("Email") or ""))
        designation = norm_whitespace(str(person.get("Designation_Title") or ""))
        extension = norm_whitespace(str(person.get("Extension") or ""))
        website = norm_whitespace(str(person.get("Website") or ""))
        
        # Process list fields
        edu_lines = format_list_field(person.get("listEEdu"))
        exp_lines = format_list_field(person.get("listEExpr"))
        pub_lines = format_list_field(person.get("listPublication"))
        
        # Build document content
        content_lines = [
            f"# {display_name}",
            f"Department: {dept}",
            f"Designation: {designation}",
            f"Email: {email}",
            f"Extension: {extension}",
            f"Website: {website}",
            "",
            "## Summary",
            summary or "N/A",
            "",
            "## Education",
            *([f"- {line}" for line in edu_lines] if edu_lines else ["- N/A"]),
            "",
            "## Experience", 
            *([f"- {line}" for line in exp_lines] if exp_lines else ["- N/A"]),
            "",
            "## Publications",
            *([f"- {line}" for line in pub_lines] if pub_lines else ["- N/A"]),
        ]
        
        page_content = "\n".join(content_lines)
        metadata = {
            "source": f"faculty:{person.get('Emp_ID')}",
            "name": display_name,
            "dept": dept,
            "email": email,
            "designation": designation,
            "emp_id": person.get("Emp_ID"),
        }
        
        return Document(page_content=page_content, metadata=metadata)


class GeneralDataProcessor(DataProcessor):
    """Processor for general university markdown files."""
    
    @staticmethod
    def process_data(source_path: str) -> List[Document]:
        """Process markdown files from directory into documents."""
        if not os.path.isdir(source_path):
            raise FileNotFoundError(f"General data directory not found: {source_path}")
        
        documents = []
        import concurrent.futures

        # Get all markdown files
        filepaths = [
            os.path.join(source_path, f)
            for f in os.listdir(source_path)
            if f.endswith('.md')
        ]
        
        def load_single_file(filepath):
            try:
                loader = UnstructuredMarkdownLoader(filepath)
                docs = loader.load()
                for doc in docs:
                    doc.metadata["source"] = filepath
                return docs
            except Exception as e:
                # logger.warning(f"Error loading file {filepath}: {e}")
                return []
        
        # Load files in parallel
        # Suppress "Need to load profiles" messages from unstructured library
        import sys
        import io
        
        # Temporarily redirect stderr to suppress unstructured library messages
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                results = executor.map(load_single_file, filepaths)
                for result in results:
                    documents.extend(result)
        finally:
            # Restore original stderr
            sys.stderr = old_stderr
        
        return documents


class VectorStoreManager:
    """Centralized vector store management system."""
    
    def __init__(self, base_data_dir: str = "data", embeddings=None):
        self.base_data_dir = base_data_dir
        self.vector_stores_dir = os.path.join(base_data_dir, "vector_stores")
        self.embeddings = embeddings
        
        # Ensure directories exist
        os.makedirs(self.vector_stores_dir, exist_ok=True)
        
        # Data processors
        self.processors = {
            VectorStoreType.DEGREE_PROGRAMS: DegreeDataProcessor(),
            VectorStoreType.FACULTY: FacultyDataProcessor(),
            VectorStoreType.GENERAL: GeneralDataProcessor(),
            VectorStoreType.EXAMS: ExamDataProcessor(),
        }
        
        # Default configurations
        self.configs = {
            VectorStoreType.DEGREE_PROGRAMS: VectorStoreConfig(
                store_type=VectorStoreType.DEGREE_PROGRAMS,
                persist_dir=os.path.join(self.vector_stores_dir, "degree_programs"),
                data_source=os.path.join(base_data_dir, "degree_programs", "degree_programs.json"),
                chunk_size=1000,
                chunk_overlap=200,
                bm25_k=15,
                embed_k=15,
                mmr_k=15,
                ensemble_weights=(0.5, 0.3, 0.2)
            ),
            VectorStoreType.FACULTY: VectorStoreConfig(
                store_type=VectorStoreType.FACULTY,
                persist_dir=os.path.join(self.vector_stores_dir, "faculty"),
                data_source=os.path.join(base_data_dir, "faculty"),
                chunk_size=800,
                chunk_overlap=150,
                bm25_k=12,
                embed_k=12,
                mmr_k=12,
                ensemble_weights=(0.5, 0.3, 0.2)
            ),
            VectorStoreType.GENERAL: VectorStoreConfig(
                store_type=VectorStoreType.GENERAL,
                persist_dir=os.path.join(self.vector_stores_dir, "general"),
                data_source=os.path.join(base_data_dir, "general", "raw"),
                chunk_size=1500,  # Increased to capture complete procedures
                chunk_overlap=300,  # Increased overlap to ensure continuity
                bm25_k=20,  # Retrieve more documents for better coverage
                embed_k=20,  # Retrieve more documents for better coverage
                mmr_k=20,  # Retrieve more documents for better coverage
                ensemble_weights=(0.5, 0.3, 0.2)
            ),
            VectorStoreType.EXAMS: VectorStoreConfig(
                store_type=VectorStoreType.EXAMS,
                persist_dir=os.path.join(self.vector_stores_dir, "exams"),
                data_source=os.path.join(base_data_dir, "structured_exams.json"),
                chunk_size=500,
                chunk_overlap=100,
                bm25_k=20,
                embed_k=20,
                mmr_k=20,
                ensemble_weights=(0.5, 0.3, 0.2)
            )
        }
    
    def get_vector_store(self, store_type: VectorStoreType) -> Optional[Chroma]:
        """Load existing vector store or return None if not found."""
        config = self.configs[store_type]
        
        try:
            if os.path.exists(config.persist_dir):
                vector_store = Chroma(
                    persist_directory=config.persist_dir,
                    embedding_function=self.embeddings
                )
                return vector_store
        except Exception as e:
            # logger.error(f"Error loading vector store {store_type.value}: {e}")
            pass
        
        return None
    
    def create_vector_store(self, store_type: VectorStoreType, force_recreate: bool = False) -> Chroma:
        """Create or recreate vector store from data source."""
        config = self.configs[store_type]
        processor = self.processors[store_type]
        
        # Check if vector store exists and force_recreate is False
        if not force_recreate and self.get_vector_store(store_type) is not None:
            # logger.info(f"Vector store {store_type.value} already exists, loading existing")
            return self.get_vector_store(store_type)
        
        # Validate data source
        if not processor.validate_source(config.data_source):
            raise FileNotFoundError(f"Data source not found: {config.data_source}")
        
        # logger.info(f"Creating vector store for {store_type.value}...")
        
        # Remove existing directory if recreating
        if force_recreate and os.path.exists(config.persist_dir):
            shutil.rmtree(config.persist_dir)
        
        # Process data into documents
        documents = processor.process_data(config.data_source)
        # logger.info(f"Processed {len(documents)} documents from {config.data_source}")
        
        # Split documents
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=["\n\n", "\n", ". ", " "]
        )
        split_docs = text_splitter.split_documents(documents)
        # logger.info(f"Split into {len(split_docs)} chunks")
        
        # Create vector store
        try:
            vector_store = Chroma.from_documents(
                split_docs,
                self.embeddings,
                persist_directory=config.persist_dir
            )
        except Exception as e:
            # Some environments may keep a read-only lock on DuckDB/Parquet files between tests.
            # If we hit a read-only database error, fall back to opening the existing store read-only.
            if "readonly" in str(e).lower():
                vector_store = Chroma(
                    persist_directory=config.persist_dir,
                    embedding_function=self.embeddings,
                )
            else:
                raise
        
        # logger.info(f"Successfully created vector store {store_type.value} with {len(split_docs)} chunks")
        return vector_store
    
    def get_retriever(self, store_type: VectorStoreType, use_ensemble: bool = True) -> Any:
        """Get retriever for the specified vector store type."""
        config = self.configs[store_type]
        vector_store = self.get_vector_store(store_type)
        
        if vector_store is None:
            # logger.info(f"Vector store {store_type.value} not found, creating...")
            vector_store = self.create_vector_store(store_type)
        
        if not use_ensemble:
            # Return simple similarity retriever
            return vector_store.as_retriever(
                search_type="similarity",
                search_kwargs={"k": config.embed_k}
            )
        
        # Create ensemble retriever with BM25 + similarity + MMR
        # For ensemble, we need the split documents for BM25
        processor = self.processors[store_type]
        documents = processor.process_data(config.data_source)
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=["\n\n", "\n", ". ", " "]
        )
        split_docs = text_splitter.split_documents(documents)
        
        # Create BM25 retriever
        bm25_retriever = BM25Retriever.from_documents(split_docs)
        bm25_retriever.k = config.bm25_k
        
        # Create embedding-based retrievers
        similarity_retriever = vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": config.embed_k}
        )
        
        mmr_retriever = vector_store.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": config.mmr_k,
                "fetch_k": config.mmr_fetch_k,
                "lambda_mult": config.mmr_lambda
            }
        )
        
        # Combine into ensemble
        ensemble_retriever = EnsembleRetriever(
            retrievers=[bm25_retriever, similarity_retriever, mmr_retriever],
            weights=list(config.ensemble_weights)
        )
        
        return ensemble_retriever

    def add_documents_to_store(self, store_type: VectorStoreType, documents: List[Document]) -> int:
        """Add documents to an existing vector store, creating it if needed.

        Returns the number of chunks added.
        """
        config = self.configs[store_type]

        # Ensure vector store exists
        vector_store = self.get_vector_store(store_type)
        if vector_store is None:
            vector_store = self.create_vector_store(store_type)

        # Split incoming documents using configured splitter
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=["\n\n", "\n", ". ", " "]
        )
        split_docs = text_splitter.split_documents(documents)

        # Add to store and persist
        vector_store.add_documents(split_docs)

        try:
            # Chroma persists automatically on add in most cases; ensure flush by reloading
            _ = self.get_vector_store(store_type)
        except Exception:
            pass

        return len(split_docs)
    
    def refresh_data(self, store_types: Optional[List[VectorStoreType]] = None) -> Dict[VectorStoreType, bool]:
        """Refresh vector stores by running scrapers and rebuilding stores.
        
        Args:
            store_types: List of store types to refresh, or None for all
            
        Returns:
            Dict mapping store types to success status
        """
        if store_types is None:
            store_types = list(VectorStoreType)
        
        results = {}
        
        for store_type in store_types:
            try:
                # logger.info(f"Refreshing vector store: {store_type.value}")
                
                # Run appropriate scraper
                scraper_success = self._run_scraper(store_type)
                if not scraper_success:
                    # logger.error(f"Failed to run scraper for {store_type.value}")
                    results[store_type] = False
                    continue
                
                # Recreate vector store
                self.create_vector_store(store_type, force_recreate=True)
                results[store_type] = True
                # logger.info(f"Successfully refreshed {store_type.value}")
                
            except Exception as e:
                # logger.error(f"Error refreshing {store_type.value}: {e}")
                results[store_type] = False
        
        return results
    
    def _run_scraper(self, store_type: VectorStoreType) -> bool:
        """Run the appropriate scraper for the given store type."""
        import subprocess
        import sys
        
        scraper_map = {
            VectorStoreType.DEGREE_PROGRAMS: "scrapers/degree_scraper.py",
            VectorStoreType.FACULTY: "scrapers/faculty_scraper.py", 
            VectorStoreType.GENERAL: "scrapers/general_scraper.py",
        }
        
        scraper_path = scraper_map.get(store_type)
        if not scraper_path or not os.path.exists(scraper_path):
            # logger.error(f"Scraper not found: {scraper_path}")
            return False
        
        try:
            result = subprocess.run(
                [sys.executable, scraper_path],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # logger.info(f"Scraper {scraper_path} completed successfully")
                return True
            else:
                # logger.error(f"Scraper {scraper_path} failed with code {result.returncode}")
                # logger.error(f"Error output: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            # logger.error(f"Scraper {scraper_path} timed out")
            return False
        except Exception as e:
            # logger.error(f"Error running scraper {scraper_path}: {e}")
            return False
    
    def get_store_info(self, store_type: VectorStoreType) -> Dict[str, Any]:
        """Get information about a vector store."""
        config = self.configs[store_type]
        vector_store = self.get_vector_store(store_type)
        
        info = {
            "type": store_type.value,
            "persist_dir": config.persist_dir,
            "data_source": config.data_source,
            "exists": vector_store is not None,
            "data_source_exists": os.path.exists(config.data_source)
        }
        
        if vector_store is not None:
            try:
                # Try to get collection info
                collection = vector_store._collection
                info["document_count"] = collection.count()
            except:
                info["document_count"] = "unknown"
        
        return info
    
    def list_all_stores(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all vector stores."""
        return {
            store_type.value: self.get_store_info(store_type)
            for store_type in VectorStoreType
        }


# Utility functions for backward compatibility and easy access
def get_vector_store_manager(embeddings=None) -> VectorStoreManager:
    """Get a configured vector store manager instance."""
    return VectorStoreManager(embeddings=embeddings)


def create_admin_refresh_function():
    """Create an admin function for refreshing data."""
    def admin_refresh_data(store_types: Optional[List[str]] = None, embeddings=None) -> Dict[str, bool]:
        """Admin function to refresh vector store data.
        
        Args:
            store_types: List of store type names to refresh (e.g., ['degree_programs', 'faculty'])
                        or None to refresh all stores
            embeddings: Embedding model to use
            
        Returns:
            Dict mapping store type names to success status
        """
        manager = get_vector_store_manager(embeddings)
        
        # Convert string names to enum values
        if store_types is not None:
            enum_types = []
            for name in store_types:
                try:
                    enum_types.append(VectorStoreType(name))
                except ValueError:
                    # logger.error(f"Unknown store type: {name}")
                    continue
        else:
            enum_types = None
        
        results = manager.refresh_data(enum_types)
        
        # Convert back to string keys for return
        return {store_type.value: success for store_type, success in results.items()}
    
    return admin_refresh_data


if __name__ == "__main__":
    # Example usage and testing
    import argparse
    from config import embeddings
    
    parser = argparse.ArgumentParser(description="Vector Store Manager")
    parser.add_argument("--action", choices=["create", "refresh", "info"], default="info")
    parser.add_argument("--store-type", choices=[t.value for t in VectorStoreType], help="Specific store type")
    parser.add_argument("--force", action="store_true", help="Force recreate existing stores")
    
    args = parser.parse_args()
    
    manager = get_vector_store_manager(embeddings)
    
    if args.action == "info":
        if args.store_type:
            store_type = VectorStoreType(args.store_type)
            info = manager.get_store_info(store_type)
            print(f"Store info for {args.store_type}:")
            for key, value in info.items():
                print(f"  {key}: {value}")
        else:
            print("All vector stores:")
            all_info = manager.list_all_stores()
            for store_name, info in all_info.items():
                print(f"\n{store_name}:")
                for key, value in info.items():
                    print(f"  {key}: {value}")
    
    elif args.action == "create":
        if args.store_type:
            store_type = VectorStoreType(args.store_type)
            manager.create_vector_store(store_type, force_recreate=args.force)
        else:
            for store_type in VectorStoreType:
                manager.create_vector_store(store_type, force_recreate=args.force)
    
    elif args.action == "refresh":
        store_types = [VectorStoreType(args.store_type)] if args.store_type else None
        results = manager.refresh_data(store_types)
        print("Refresh results:")
        for store_type, success in results.items():
            print(f"  {store_type.value}: {'✓' if success else '✗'}")