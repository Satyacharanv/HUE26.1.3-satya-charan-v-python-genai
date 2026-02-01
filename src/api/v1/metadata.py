"""Metadata and code chunks API endpoints for Milestone 2"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from src.database import get_db
from src.api.deps import get_current_user
from src.core.logging_config import get_logger
from src.models.user import User
from src.models.project import Project
from src.models.code_chunk import CodeChunk
from src.models.repository_metadata import RepositoryMetadata, FileMetadata
from src.core.exceptions import ProjectNotFoundException
from src.schemas.metadata import (
    RepositoryMetadataResponse,
    CodeChunkResponse,
    CodeChunkListResponse,
    FileMetadataResponse,
    FileMetadataListResponse,
    RepositoryIntelligenceResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/projects", tags=["metadata"])


@router.get("/{project_id}/metadata", response_model=RepositoryMetadataResponse)
async def get_repository_metadata(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get repository metadata and intelligence for a project"""
    logger.debug(f"Getting metadata for project {project_id} (user: {current_user.id})")
    
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        logger.warning(f"Project {project_id} not found or not owned by user {current_user.id}")
        raise ProjectNotFoundException(str(project_id))
    
    # Get repository metadata
    result = await db.execute(
        select(RepositoryMetadata).where(RepositoryMetadata.project_id == project_id)
    )
    metadata = result.scalar_one_or_none()
    
    if not metadata:
        logger.warning(f"Repository metadata not found for project {project_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository metadata not found. Has preprocessing been completed?"
        )
    
    logger.debug(f"Metadata retrieved for project {project_id}")
    return metadata


@router.get("/{project_id}/files", response_model=FileMetadataListResponse)
async def list_project_files(
    project_id: UUID,
    skip: int = 0,
    limit: int = 100,
    important_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List files in a project with metadata"""
    logger.debug(f"Listing files for project {project_id} (skip={skip}, limit={limit})")
    
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise ProjectNotFoundException(str(project_id))
    
    # Build query
    query = select(FileMetadata).where(FileMetadata.project_id == project_id)
    
    if important_only:
        query = query.where(FileMetadata.is_important == True)
    
    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(FileMetadata).where(FileMetadata.project_id == project_id)
    )
    total = count_result.scalar()
    
    # Get paginated results
    query = query.order_by(FileMetadata.file_path).offset(skip).limit(limit)
    result = await db.execute(query)
    files = result.scalars().all()
    
    logger.debug(f"Retrieved {len(files)} files for project {project_id}")
    
    return FileMetadataListResponse(
        files=files,
        total=total,
        project_id=project_id
    )


@router.get("/{project_id}/files/{file_path:path}", response_model=FileMetadataResponse)
async def get_file_metadata(
    project_id: UUID,
    file_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get metadata for a specific file"""
    logger.debug(f"Getting metadata for file: {file_path}")
    
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise ProjectNotFoundException(str(project_id))
    
    # Get file metadata
    result = await db.execute(
        select(FileMetadata).where(
            FileMetadata.project_id == project_id,
            FileMetadata.file_path == file_path
        )
    )
    file_meta = result.scalar_one_or_none()
    
    if not file_meta:
        logger.warning(f"File metadata not found: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {file_path}"
        )
    
    return file_meta


@router.get("/{project_id}/chunks", response_model=CodeChunkListResponse)
async def list_project_chunks(
    project_id: UUID,
    skip: int = 0,
    limit: int = 50,
    chunk_type: str = None,
    language: str = None,
    important_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List code chunks for a project with optional filtering"""
    logger.debug(f"Listing chunks for project {project_id} (type={chunk_type}, language={language})")
    
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise ProjectNotFoundException(str(project_id))
    
    # Build query
    query = select(CodeChunk).where(CodeChunk.project_id == project_id)
    
    if chunk_type:
        query = query.where(CodeChunk.chunk_type == chunk_type)
    
    if language:
        query = query.where(CodeChunk.language == language)
    
    if important_only:
        query = query.where(CodeChunk.is_important == True)
    
    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(CodeChunk).where(CodeChunk.project_id == project_id)
    )
    total = count_result.scalar()
    
    # Get paginated results
    query = query.order_by(CodeChunk.file_path, CodeChunk.start_line).offset(skip).limit(limit)
    result = await db.execute(query)
    chunks = result.scalars().all()
    
    logger.debug(f"Retrieved {len(chunks)} chunks for project {project_id}")
    
    return CodeChunkListResponse(
        chunks=chunks,
        total=total,
        project_id=project_id
    )


@router.get("/{project_id}/chunks/{chunk_id}", response_model=CodeChunkResponse)
async def get_chunk(
    project_id: UUID,
    chunk_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific code chunk with full details"""
    logger.debug(f"Getting chunk {chunk_id}")
    
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise ProjectNotFoundException(str(project_id))
    
    # Get chunk
    result = await db.execute(
        select(CodeChunk).where(
            CodeChunk.id == chunk_id,
            CodeChunk.project_id == project_id
        )
    )
    chunk = result.scalar_one_or_none()
    
    if not chunk:
        logger.warning(f"Chunk not found: {chunk_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chunk not found"
        )
    
    return chunk


@router.get("/{project_id}/intelligence", response_model=RepositoryIntelligenceResponse)
async def get_repository_intelligence(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get complete repository intelligence summary"""
    logger.debug(f"Getting intelligence for project {project_id}")
    
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise ProjectNotFoundException(str(project_id))
    
    # Get repository metadata
    result = await db.execute(
        select(RepositoryMetadata).where(RepositoryMetadata.project_id == project_id)
    )
    repo_metadata = result.scalar_one_or_none()
    
    if not repo_metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not preprocessed"
        )
    
    # Get all files
    result = await db.execute(
        select(FileMetadata).where(FileMetadata.project_id == project_id)
    )
    all_files = result.scalars().all()
    
    # Get important files
    important_files = [f for f in all_files if f.is_important]
    
    # Get code chunks summary
    result = await db.execute(
        select(CodeChunk.chunk_type, func.count()).where(
            CodeChunk.project_id == project_id
        ).group_by(CodeChunk.chunk_type)
    )
    chunk_type_counts = dict(result.all())
    
    result = await db.execute(
        select(CodeChunk.language, func.count()).where(
            CodeChunk.project_id == project_id
        ).group_by(CodeChunk.language)
    )
    language_counts = dict(result.all())
    
    chunks_summary = {
        "by_type": chunk_type_counts,
        "by_language": language_counts,
        "total": sum(chunk_type_counts.values()),
    }
    
    return RepositoryIntelligenceResponse(
        repository_metadata=repo_metadata,
        files=all_files,
        important_files=important_files,
        code_chunks_summary=chunks_summary
    )


@router.get("/{project_id}/chunks/search")
async def search_chunks(
    project_id: UUID,
    query: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search code chunks by semantic similarity (using pgvector)"""
    logger.debug(f"Searching chunks for project {project_id}: {query}")
    
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise ProjectNotFoundException(str(project_id))
    
    # TODO: Implement semantic search with pgvector
    # For now, return empty or simple text search
    
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Semantic search coming in Milestone 3"
    )


@router.post("/{project_id}/preprocess")
async def trigger_preprocessing(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Trigger intelligent preprocessing for a project
    
    This endpoint starts the Code Chunker pipeline which:
    1. Analyzes repository type and frameworks
    2. Parses code files in all supported languages
    3. Generates semantic chunks (functions, classes, etc.)
    4. Creates embeddings using OpenAI
    5. Stores metadata in pgvector
    """
    from src.services.code_chunker import CodeChunker
    
    logger.info(f"Starting preprocessing for project {project_id} (user: {current_user.id})")
    
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        logger.warning(f"Project {project_id} not found or not owned by user {current_user.id}")
        raise ProjectNotFoundException(str(project_id))
    
    try:
        # Start preprocessing pipeline
        code_chunker = CodeChunker(db)
        result = await code_chunker.preprocess_project(project, current_user)
        
        logger.info(f"Preprocessing started for project {project_id}")
        return {
            "status": "preprocessing_started",
            "project_id": str(project_id),
            "message": f"Preprocessing pipeline initiated. Total chunks: {result.get('total_chunks', 0)}"
        }
    except Exception as e:
        logger.error(f"Error starting preprocessing: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start preprocessing: {str(e)}"
        )
