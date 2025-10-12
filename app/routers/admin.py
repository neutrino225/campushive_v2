import os
import sys
import asyncio
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

# Add root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from vector_store_manager import VectorStoreManager, VectorStoreType
from config import embeddings
from app.database import get_db, User, UploadedExam
from app.auth.dependencies import require_admin
from langchain.text_splitter import RecursiveCharacterTextSplitter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global manager instance (will be managed by the main app's lifespan)
vector_manager: Optional[VectorStoreManager] = None

def set_vector_manager(manager: VectorStoreManager):
    """Set the global vector manager instance from the main app."""
    global vector_manager
    vector_manager = manager

# Create an APIRouter
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)

# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=3)


# Pydantic models for request/response
class VectorStoreInfo(BaseModel):
    """Information about a vector store."""
    type: str
    persist_dir: str
    data_source: str
    exists: bool
    data_source_exists: bool
    document_count: Optional[Union[int, str]] = None


class CreateStoreRequest(BaseModel):
    """Request model for creating vector stores."""
    force: bool = Field(default=False, description="Force recreate existing store")


class RefreshDataRequest(BaseModel):
    """Request model for refreshing data."""
    store_types: Optional[List[str]] = Field(
        default=None, 
        description="List of store types to refresh. If None, refreshes all stores."
    )
    
    @validator('store_types')
    def validate_store_types(cls, v):
        if v is not None:
            valid_types = [t.value for t in VectorStoreType]
            for store_type in v:
                if store_type not in valid_types:
                    raise ValueError(f"Invalid store type: {store_type}. Valid types: {valid_types}")
        return v


class BatchOperationRequest(BaseModel):
    """Request model for batch operations."""
    action: str = Field(..., description="Action to perform: 'create' or 'info'")
    store_types: List[str] = Field(..., description="List of store types to operate on")
    force: bool = Field(default=False, description="Force recreate for create action")
    
    @validator('action')
    def validate_action(cls, v):
        if v not in ['create', 'info']:
            raise ValueError("Action must be 'create' or 'info'")
        return v
    
    @validator('store_types')
    def validate_store_types(cls, v):
        valid_types = [t.value for t in VectorStoreType]
        for store_type in v:
            if store_type not in valid_types:
                raise ValueError(f"Invalid store type: {store_type}. Valid types: {valid_types}")
        return v


class OperationResponse(BaseModel):
    """Standard response model for operations."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class UploadedExamResponse(BaseModel):
    id: int
    filename: str
    course_name: str
    exam_type: str
    uploaded_by: int
    uploaded_at: datetime
    status: str
    file_path: str

    class Config:
        from_attributes = True


class BatchOperationResponse(BaseModel):
    """Response model for batch operations."""
    overall_success: bool
    results: Dict[str, Dict[str, Any]]
    summary: str
    timestamp: datetime = Field(default_factory=datetime.now)


# Dependency to get manager
def get_vector_manager() -> VectorStoreManager:
    """Get the global vector store manager instance."""
    if vector_manager is None:
        # This should be initialized by the main app's lifespan manager
        # A custom dependency could be created to share the manager instance
        # For now, we rely on the main app to set it.
        try:
            # Fallback initialization if not set (e.g., for standalone testing)
            return VectorStoreManager(embeddings=embeddings)
        except Exception as e:
            logger.error(f"Failed to initialize Vector Store Manager on-the-fly: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Vector Store Manager not initialized"
            )
    return vector_manager


def _save_upload_to_disk(base_dir: str, course_name: str, exam_type: str, file: UploadFile) -> str:
    """Save uploaded file to disk and return file path."""
    os.makedirs(os.path.join(base_dir, course_name), exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_course = course_name.replace("/", "-").strip()
    safe_type = exam_type.replace("/", "-").strip()
    filename = f"{safe_course}_{safe_type}_{ts}.pdf"
    dest_path = os.path.join(base_dir, safe_course, filename)
    with open(dest_path, "wb") as out:
        out.write(file.file.read())
    return dest_path


@router.post("/exams/upload", response_model=OperationResponse)
async def upload_exam(
    background_tasks: BackgroundTasks,
    course_name: str = Form(...),
    exam_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    manager: VectorStoreManager = Depends(get_vector_manager),
    current_user: User = Depends(require_admin),
):
    """Upload an exam PDF for a course; enqueue processing and tracking."""
    try:
        # Basic validations
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are allowed")

        # Save to disk
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "exams"))
        dest_path = _save_upload_to_disk(base_dir, course_name, exam_type, file)

        # Create DB record with processing status
        record = UploadedExam(
            filename=os.path.basename(dest_path),
            course_name=course_name,
            exam_type=exam_type,
            uploaded_by=current_user.id,
            status="processing",
            file_path=dest_path,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        # Background processing: parse, update structured_exams.json, add to vector store (centralized)
        def process_upload(upload_id: int, path: str, course: str, e_type: str):
            try:
                # Use centralized utils for parsing and conversion
                from app.utils.exams import (
                    analyze_pdf_to_structured,
                    structured_exam_to_documents,
                    append_structured_exam_to_json,
                )

                structured = analyze_pdf_to_structured(path, course)
                if structured is None:
                    raise RuntimeError("Exam analysis failed")

                # Append to structured exams JSON
                struct_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "structured_exams.json"))
                append_structured_exam_to_json(structured, struct_path)

                # Convert to Documents
                docs = structured_exam_to_documents(structured, path)

                # Centralized add via manager
                manager.add_documents_to_store(VectorStoreType.EXAMS, docs)

                # Mark processed
                with next(get_db()) as session:
                    rec = session.query(UploadedExam).filter(UploadedExam.id == upload_id).first()
                    if rec:
                        rec.status = "processed"
                        session.commit()
            except Exception:
                # Mark failed
                with next(get_db()) as session:
                    rec = session.query(UploadedExam).filter(UploadedExam.id == upload_id).first()
                    if rec:
                        rec.status = "failed"
                        session.commit()

        await asyncio.get_event_loop().run_in_executor(
            executor,
            process_upload,
            record.id,
            dest_path,
            course_name,
            exam_type,
        )

        return OperationResponse(
            success=True,
            message="Upload accepted and processing started",
            data={"upload_id": record.id}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading exam: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload exam")


@router.get("/exams/list", response_model=List[UploadedExamResponse])
async def list_uploaded_exams(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List uploaded exams for admin tracking."""
    rows = db.query(UploadedExam).order_by(UploadedExam.uploaded_at.desc()).all()
    return [UploadedExamResponse.model_validate(r) for r in rows]


# Health check endpoints
@router.get("/health", response_model=Dict[str, str])
async def health_check():
    """Health check endpoint for the admin router."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Admin Router"
    }


@router.get("/health/vector-stores", response_model=Dict[str, Any])
async def vector_stores_health(manager: VectorStoreManager = Depends(get_vector_manager)):
    """Check health of all vector stores."""
    try:
        all_stores = manager.list_all_stores()
        
        total_stores = len(all_stores)
        healthy_stores = sum(1 for info in all_stores.values() if info['exists'] and info['data_source_exists'])
        
        return {
            "status": "healthy" if healthy_stores == total_stores else "degraded",
            "total_stores": total_stores,
            "healthy_stores": healthy_stores,
            "stores": all_stores,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error checking vector stores health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking vector stores health: {str(e)}"
        )


# Vector store information endpoints
@router.get("/vector-stores", response_model=Dict[str, VectorStoreInfo])
async def get_all_vector_stores(
    manager: VectorStoreManager = Depends(get_vector_manager),
    current_user: User = Depends(require_admin)
):
    """Get information about all vector stores."""
    try:
        all_stores = manager.list_all_stores()
        
        result = {}
        for store_name, info in all_stores.items():
            result[store_name] = VectorStoreInfo(
                type=store_name,
                persist_dir=info['persist_dir'],
                data_source=info['data_source'],
                exists=info['exists'],
                data_source_exists=info['data_source_exists'],
                document_count=info.get('document_count')
            )
        
        return result
    except Exception as e:
        logger.error(f"Error getting vector stores info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving vector stores information: {str(e)}"
        )


@router.get("/vector-stores/{store_type}", response_model=VectorStoreInfo)
async def get_vector_store_info(
    store_type: str,
    manager: VectorStoreManager = Depends(get_vector_manager),
    current_user: User = Depends(require_admin)
):
    """Get information about a specific vector store."""
    try:
        # Validate store type
        try:
            store_enum = VectorStoreType(store_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid store type: {store_type}. Valid types: {[t.value for t in VectorStoreType]}"
            )
        
        info = manager.get_store_info(store_enum)
        
        return VectorStoreInfo(
            type=store_type,
            persist_dir=info['persist_dir'],
            data_source=info['data_source'],
            exists=info['exists'],
            data_source_exists=info['data_source_exists'],
            document_count=info.get('document_count')
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting vector store info for {store_type}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving vector store information: {str(e)}"
        )


# Vector store creation endpoints
@router.post("/vector-stores/{store_type}/create", response_model=OperationResponse)
async def create_vector_store(
    store_type: str,
    request: CreateStoreRequest,
    background_tasks: BackgroundTasks,
    manager: VectorStoreManager = Depends(get_vector_manager),
    current_user: User = Depends(require_admin)
):
    """Create or recreate a specific vector store."""
    try:
        # Validate store type
        try:
            store_enum = VectorStoreType(store_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid store type: {store_type}. Valid types: {[t.value for t in VectorStoreType]}"
            )
        
        # Run creation in background for large operations
        def create_store():
            try:
                manager.create_vector_store(store_enum, force_recreate=request.force)
                logger.info(f"Successfully created vector store: {store_type}")
            except Exception as e:
                logger.error(f"Error creating vector store {store_type}: {e}")
                raise
        
        await asyncio.get_event_loop().run_in_executor(executor, create_store)
        
        return OperationResponse(
            success=True,
            message=f"Vector store '{store_type}' created successfully",
            data={"store_type": store_type, "force": request.force}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating vector store {store_type}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating vector store: {str(e)}"
        )


@router.post("/vector-stores/{store_type}/rebuild", response_model=OperationResponse)
async def rebuild_vector_store(
    store_type: str,
    background_tasks: BackgroundTasks,
    manager: VectorStoreManager = Depends(get_vector_manager),
    current_user: User = Depends(require_admin)
):
    """Rebuild (recreate) a specific vector store."""
    try:
        # Validate store type
        try:
            store_enum = VectorStoreType(store_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vector store type not found: {store_type}"
            )
        
        # Run rebuild in background
        def rebuild_store():
            try:
                manager.create_vector_store(store_enum, force_recreate=True)
                logger.info(f"Successfully rebuilt vector store: {store_type}")
            except Exception as e:
                logger.error(f"Error rebuilding vector store {store_type}: {e}")
                raise
        
        await asyncio.get_event_loop().run_in_executor(executor, rebuild_store)
        
        return OperationResponse(
            success=True,
            message=f"Vector store '{store_type}' rebuilt successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rebuilding vector store {store_type}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rebuilding vector store: {str(e)}"
        )


@router.get("/vector-stores/{store_type}/stats", response_model=Dict[str, Any])
async def get_vector_store_stats(
    store_type: str,
    manager: VectorStoreManager = Depends(get_vector_manager),
    current_user: User = Depends(require_admin)
):
    """Get statistics for a specific vector store."""
    try:
        # Validate store type
        try:
            store_enum = VectorStoreType(store_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vector store type not found: {store_type}"
            )
        
        info = manager.get_store_info(store_enum)
        
        return {
            "store_type": store_type,
            "exists": info['exists'],
            "data_source_exists": info['data_source_exists'],
            "document_count": info.get('document_count', 0),
            "persist_dir": info['persist_dir'],
            "data_source": info['data_source']
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stats for {store_type}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving vector store stats: {str(e)}"
        )


@router.delete("/vector-stores/{store_type}", response_model=OperationResponse)
async def delete_vector_store(
    store_type: str,
    manager: VectorStoreManager = Depends(get_vector_manager),
    current_user: User = Depends(require_admin)
):
    """Delete (clear) a specific vector store."""
    try:
        # Validate store type
        try:
            store_enum = VectorStoreType(store_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vector store type not found: {store_type}"
            )
        
        # Get persist directory and delete it
        info = manager.get_store_info(store_enum)
        persist_dir = info['persist_dir']
        
        if info['exists']:
            import shutil
            shutil.rmtree(persist_dir)
            logger.info(f"Successfully deleted vector store: {store_type}")
            return OperationResponse(
                success=True,
                message=f"Vector store '{store_type}' deleted successfully"
            )
        else:
            return OperationResponse(
                success=True,
                message=f"Vector store '{store_type}' does not exist, nothing to delete"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting vector store {store_type}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting vector store: {str(e)}"
        )


# Data refresh endpoints
@router.post("/vector-stores/refresh", response_model=OperationResponse)
async def refresh_vector_stores(
    request: RefreshDataRequest,
    background_tasks: BackgroundTasks,
    manager: VectorStoreManager = Depends(get_vector_manager),
    current_user: User = Depends(require_admin)
):
    """Refresh vector stores by running scrapers and rebuilding stores."""
    try:
        # Convert string store types to enums
        target_types = None
        if request.store_types:
            target_types = [VectorStoreType(st) for st in request.store_types]
        
        # Run refresh in background
        def refresh_data():
            try:
                results = manager.refresh_data(target_types)
                logger.info(f"Data refresh completed. Results: {results}")
                return results
            except Exception as e:
                logger.error(f"Error during data refresh: {e}")
                raise
        
        results = await asyncio.get_event_loop().run_in_executor(executor, refresh_data)
        
        # Format results
        formatted_results = {k.value: v for k, v in results.items()}
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)
        
        return OperationResponse(
            success=success_count == total_count,
            message=f"Data refresh completed. {success_count}/{total_count} stores refreshed successfully.",
            data={
                "results": formatted_results,
                "summary": {
                    "total": total_count,
                    "successful": success_count,
                    "failed": total_count - success_count
                }
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing vector stores: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error refreshing vector stores: {str(e)}"
        )


# Batch operations
@router.post("/vector-stores/batch", response_model=BatchOperationResponse)
async def batch_operations(
    request: BatchOperationRequest,
    background_tasks: BackgroundTasks,
    manager: VectorStoreManager = Depends(get_vector_manager),
    current_user: User = Depends(require_admin)
):
    """Perform batch operations on multiple vector stores."""
    try:
        # Convert string store types to enums
        store_enums = [VectorStoreType(st) for st in request.store_types]
        
        results = {}
        
        if request.action == "create":
            # Batch create stores
            def create_stores():
                batch_results = {}
                for store_enum in store_enums:
                    try:
                        manager.create_vector_store(store_enum, force_recreate=request.force)
                        batch_results[store_enum.value] = {
                            "success": True,
                            "message": f"Vector store '{store_enum.value}' created successfully"
                        }
                    except Exception as e:
                        batch_results[store_enum.value] = {
                            "success": False,
                            "error": str(e),
                            "message": f"Failed to create vector store '{store_enum.value}'"
                        }
                return batch_results
            
            results = await asyncio.get_event_loop().run_in_executor(executor, create_stores)
        
        elif request.action == "info":
            # Batch get info
            for store_enum in store_enums:
                try:
                    info = manager.get_store_info(store_enum)
                    results[store_enum.value] = {
                        "success": True,
                        "info": info
                    }
                except Exception as e:
                    results[store_enum.value] = {
                        "success": False,
                        "error": str(e)
                    }
        
        # Calculate summary
        successful = sum(1 for result in results.values() if result.get("success", False))
        total = len(results)
        
        return BatchOperationResponse(
            overall_success=successful == total,
            results=results,
            summary=f"Batch {request.action} completed. {successful}/{total} operations successful."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch operations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in batch operations: {str(e)}"
        )


# System information endpoints
@router.get("/system/info", response_model=Dict[str, Any])
async def get_system_info(
    manager: VectorStoreManager = Depends(get_vector_manager),
    current_user: User = Depends(require_admin)
):
    """Get system information and statistics."""
    try:
        all_stores = manager.list_all_stores()
        
        total_documents = 0
        for info in all_stores.values():
            doc_count = info.get('document_count')
            if isinstance(doc_count, int):
                total_documents += doc_count
        
        return {
            "system": {
                "api_version": "1.0.0",
                "timestamp": datetime.now().isoformat(),
                "available_store_types": [t.value for t in VectorStoreType]
            },
            "statistics": {
                "total_stores": len(all_stores),
                "active_stores": sum(1 for info in all_stores.values() if info['exists']),
                "total_documents": total_documents
            },
            "stores": all_stores
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving system information: {str(e)}"
        )
