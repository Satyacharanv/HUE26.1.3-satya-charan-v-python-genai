"""FastAPI application entry point"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.core.config import settings
from src.core.exceptions import MacadException
from src.core.logging_config import setup_logging
from src.api.v1 import auth, projects, metadata, semantic_search, analysis, websocket_progress, admin
from src.database import init_db, close_db
import uvicorn

# Set up logging
logger = setup_logging("macad.main", log_file="app.log")

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Multi-Agent Code Analysis & Documentation System",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(projects.router, prefix=settings.API_V1_PREFIX)
app.include_router(metadata.router, prefix=settings.API_V1_PREFIX)
app.include_router(semantic_search.router, prefix=settings.API_V1_PREFIX + "/projects")
app.include_router(analysis.router, prefix=settings.API_V1_PREFIX)
app.include_router(websocket_progress.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router, prefix=settings.API_V1_PREFIX)


# Global exception handler
@app.exception_handler(MacadException)
async def macad_exception_handler(request, exc: MacadException):
    """Handle custom maCAD exceptions"""
    logger.warning(f"maCAD exception: {exc.detail} - Path: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("Starting maCAD System API...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Close database connections on shutdown"""
    logger.info("Shutting down maCAD System API...")
    try:
        await close_db()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}", exc_info=True)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "maCAD System API",
        "version": "0.1.0",
        "docs": "/docs"
    }


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
