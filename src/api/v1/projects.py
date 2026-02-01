"""Project endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from src.database import get_db
from src.api.deps import get_current_user
from src.core.logging_config import get_logger
from src.schemas.project import ProjectCreate, ProjectResponse, ProjectListResponse
from src.models.project import Project, ProjectStatus
from src.models.user import User
from src.services.project_service import ProjectService
from src.core.exceptions import (
    ProjectNotFoundException,
    InvalidFileException,
    FileTooLargeException,
    CorruptedFileException,
    UnsupportedFileTypeException,
    EmptyRepositoryException
)

logger = get_logger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new project"""
    logger.info(f"Creating project '{project_data.name}' for user {current_user.id} (source: {project_data.source_type.value})")
    project_service = ProjectService(db)
    
    # Handle GitHub URL
    if project_data.source_type.value == "github":
        try:
            project = await project_service.create_from_github(
                name=project_data.name,
                github_url=project_data.source_path,
                owner_id=current_user.id,
                personas=[p.value for p in project_data.personas],
                config=project_data.config
            )
            logger.info(f"Project created successfully: {project.name} (ID: {project.id})")
        except Exception as e:
            logger.error(f"Error creating project from GitHub: {e}", exc_info=True)
            raise
    else:
        logger.warning(f"Invalid source type for /projects endpoint: {project_data.source_type.value}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZIP upload must use /projects/upload endpoint"
        )
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        owner_id=project.owner_id,
        source_type=project.source_type,
        source_path=project.source_path,
        status=project.status,
        personas=project.personas,
        config=project.config or {},
        created_at=project.created_at,
        updated_at=project.updated_at
    )


@router.post("/upload", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def upload_project(
    name: str = Form(...),
    file: UploadFile = File(...),
    personas: str = Form("sde,pm"),  # Comma-separated string
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a ZIP file to create a project"""
    logger.info(f"Uploading project '{name}' for user {current_user.id} (file: {file.filename})")
    project_service = ProjectService(db)
    
    # Parse personas
    persona_list = [p.strip().lower() for p in personas.split(",")]
    valid_personas = ["sde", "pm"]
    persona_list = [p for p in persona_list if p in valid_personas]
    
    if not persona_list:
        logger.warning(f"No valid personas selected for project '{name}'")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one persona (sde or pm) must be selected"
        )
    
    try:
        project = await project_service.create_from_zip(
            name=name,
            file=file,
            owner_id=current_user.id,
            personas=persona_list,
            config={}
        )
        logger.info(f"Project uploaded successfully: {project.name} (ID: {project.id})")
    except (InvalidFileException, FileTooLargeException, CorruptedFileException,
            UnsupportedFileTypeException, EmptyRepositoryException) as e:
        logger.warning(f"Project validation failed: {e.detail}")
        raise  # These already have proper HTTP status codes
    except Exception as e:
        logger.error(f"Unexpected error in project creation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your request"
        )
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        owner_id=project.owner_id,
        source_type=project.source_type,
        source_path=project.source_path,
        status=project.status,
        personas=project.personas,
        config=project.config or {},
        created_at=project.created_at,
        updated_at=project.updated_at
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List user's projects"""
    logger.debug(f"Listing projects for user {current_user.id} (skip: {skip}, limit: {limit})")
    
    # Get user's projects
    result = await db.execute(
        select(Project)
        .where(Project.owner_id == current_user.id)
        .order_by(Project.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    projects = result.scalars().all()
    
    # Get total count
    count_result = await db.execute(
        select(Project).where(Project.owner_id == current_user.id)
    )
    total = len(count_result.scalars().all())
    
    logger.debug(f"Found {total} projects for user {current_user.id}")
    
    return ProjectListResponse(
        projects=[
            ProjectResponse(
                id=p.id,
                name=p.name,
                owner_id=p.owner_id,
                source_type=p.source_type,
                source_path=p.source_path,
                status=p.status,
                personas=p.personas,
                config=p.config or {},
                created_at=p.created_at,
                updated_at=p.updated_at
            )
            for p in projects
        ],
        total=total
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific project"""
    logger.debug(f"Getting project {project_id} for user {current_user.id}")
    
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        logger.warning(f"Project {project_id} not found for user {current_user.id}")
        raise ProjectNotFoundException(project_id)
    
    logger.debug(f"Project {project_id} retrieved successfully")
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        owner_id=project.owner_id,
        source_type=project.source_type,
        source_path=project.source_path,
        status=project.status,
        personas=project.personas,
        config=project.config or {},
        created_at=project.created_at,
        updated_at=project.updated_at
    )


@router.post("/{project_id}/preprocess", status_code=status.HTTP_202_ACCEPTED)
async def preprocess_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Trigger preprocessing for a project"""
    from uuid import UUID
    from src.services.code_chunker import CodeChunker
    from src.services.storage import storage_service
    
    logger.info(f"Preprocessing request for project {project_id} (user: {current_user.id})")
    
    try:
        project_uuid = UUID(project_id)
    except ValueError:
        logger.error(f"Invalid project ID format: {project_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project ID format"
        )
    
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_uuid,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        logger.warning(f"Project {project_id} not found or not owned by user {current_user.id}")
        raise ProjectNotFoundException(str(project_id))
    
    # Get extracted path - use the standard location
    # When project is created, extracted files are moved to: projects/{project_id}/extracted
    from src.services.storage import storage_service
    from src.services.project_service import ProjectService
    from pathlib import Path
    from src.models.project import SourceType
    
    extracted_path = f"projects/{str(project_uuid)}/extracted"
    extracted_full_path = storage_service.get_file_path(extracted_path)
    
    logger.debug(f"Using extracted path: {extracted_path}")
    logger.debug(f"Full path: {extracted_full_path}")
    logger.debug(f"Project source type: {project.source_type}")
    
    # For GitHub projects, clone the repository if not already done
    if project.source_type == SourceType.GITHUB:
        logger.info(f"GitHub project detected - cloning repository")
        try:
            project_service = ProjectService(db)
            extracted_path = await project_service.clone_github_repo(
                str(project_uuid), 
                project.source_path  # source_path contains the GitHub URL
            )
            extracted_full_path = storage_service.get_file_path(extracted_path)
            logger.info(f"Successfully cloned GitHub repository to {extracted_full_path}")
        except Exception as e:
            logger.error(f"Failed to clone GitHub repository: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to clone GitHub repository: {str(e)}"
            )
    
    # Verify extracted files exist
    if not extracted_full_path.exists():
        logger.error(f"Extracted files not found for project {project_uuid}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project {project_id} does not have extracted files. Please try again or re-upload the project."
        )
    
    # Trigger preprocessing
    try:
        code_chunker = CodeChunker(db)
        result = await code_chunker.preprocess_project(str(project_uuid), extracted_path)
        
        logger.info(f"Preprocessing started for project {project.id}")
        return {
            "status": "preprocessing_started",
            "project_id": str(project.id),
            "message": f"Preprocessing pipeline initiated. Total chunks: {result.get('total_chunks', 0)}"
        }
    except Exception as e:
        logger.error(f"Error starting preprocessing: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting preprocessing: {str(e)}"
        )

