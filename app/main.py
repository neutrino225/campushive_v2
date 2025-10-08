import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Add root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.routers import admin, multiagent, auth, user_admin, chats
from vector_store_manager import VectorStoreManager
from config import embeddings
from app.database import Base, engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager to initialize and shut down resources.
    """
    logger.info("Application startup: Initializing database and resources...")
    try:
        # Initialize database tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized.")
        
        # Initialize the VectorStoreManager
        manager = VectorStoreManager(embeddings=embeddings)
        # Provide the manager instance to the admin router
        admin.set_vector_manager(manager)
        logger.info("Vector Store Manager initialized and set for admin router.")
    except Exception as e:
        logger.error(f"Fatal error during startup: {e}")
        # In a real application, you might want to handle this more gracefully
        # or prevent the app from starting.
        raise
    
    yield
    
    # Shutdown
    logger.info("Application shutdown: Cleaning up resources...")
    admin.set_vector_manager(None) # Clear the manager instance
    logger.info("Resources cleaned up.")


# Initialize FastAPI app
app = FastAPI(
    title="CampusHive API",
    description="Main API for CampusHive, combining admin and multi-agent functionalities.",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Include routers
app.include_router(auth.router)
app.include_router(user_admin.router)
app.include_router(chats.router)
app.include_router(admin.router)
app.include_router(multiagent.router)

# Root endpoint
@app.get("/", tags=["Root"])
async def read_root():
    """
    Serve the main chat interface.
    """
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    return FileResponse(index_path, media_type="text/html")

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Global exception handler to catch unhandled errors.
    """
    logger.error(f"Unhandled exception for request {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected internal server error occurred."}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """
    Custom handler for FastAPI's HTTPException to ensure consistent logging.
    """
    logger.warning(f"HTTP Exception for request {request.url.path}: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )
