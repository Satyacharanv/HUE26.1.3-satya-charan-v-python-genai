"""Project service - handles project creation and file validation"""
import os
import shutil
import zipfile
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from src.models.project import Project, SourceType, ProjectStatus
from src.services.storage import storage_service
from src.core.config import settings
from src.core.logging_config import get_logger
from src.core.exceptions import (
    InvalidFileException,
    FileTooLargeException,
    CorruptedFileException,
    UnsupportedFileTypeException,
    EmptyRepositoryException,
    GitHubAccessException
)

logger = get_logger(__name__)


class ProjectService:
    """Service for project operations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = storage_service
    
    async def create_from_zip(
        self,
        name: str,
        file: UploadFile,
        owner_id: int,
        personas: List[str],
        config: Optional[Dict[str, Any]] = None
    ) -> Project:
        """Create project from uploaded ZIP file"""
        logger.info(f"Creating project from ZIP: {name} (file: {file.filename}, owner: {owner_id})")
        
        stored_path = None
        try:
            # Validate file
            await self._validate_zip_file(file)
            logger.debug(f"ZIP file validation passed: {file.filename}")
            
            # Read file content
            content = await file.read()
            logger.debug(f"Read {len(content)} bytes from ZIP file")
            
            # Save uploaded file
            stored_path = self.storage.save_upload(content, file.filename)
            logger.debug(f"Saved uploaded file to: {stored_path}")
            
            try:
                # Extract ZIP to project directory
                extracted_path = self.storage.extract_zip(stored_path, owner_id)  # Temporary ID
                logger.debug(f"Extracted ZIP to: {extracted_path}")
                
                # Validate extracted content
                self._validate_extracted_repository(extracted_path)
                logger.debug("Repository validation passed")
                
                # Create project record
                project = Project(
                    name=name,
                    owner_id=owner_id,
                    source_type=SourceType.ZIP,
                    source_path=stored_path,  # Store path to original ZIP
                    status=ProjectStatus.CREATED,
                    personas=personas,
                    config=config or {}
                )
                
                self.db.add(project)
                await self.db.commit()
                await self.db.refresh(project)
                
                # Move extracted files to final project directory
                temp_extract = self.storage.get_file_path(extracted_path)
                final_extract = self.storage.projects_path / str(project.id) / "extracted"
                
                if not temp_extract.exists():
                    logger.warning(f"Temporary extracted path does not exist: {temp_extract}")
                    # This might be OK if extraction was already done, but log it
                
                if temp_extract.exists():
                    final_extract.parent.mkdir(parents=True, exist_ok=True)
                    # Use shutil.move() instead of rename() for cross-directory moves on Windows
                    shutil.move(str(temp_extract), str(final_extract))
                    logger.debug(f"Moved extracted files from {temp_extract} to {final_extract}")
                    
                    # Verify move was successful
                    if not final_extract.exists():
                        raise IOError(f"Failed to move extracted files to {final_extract}")
                
                # Verify final extracted path exists
                if not final_extract.exists():
                    raise IOError(f"Extracted files not found at {final_extract}. Extraction may have failed.")
                
                logger.info(f"Project created successfully: {project.id} with extracted files at {final_extract}")
                return project
                
            except Exception as e:
                # If extraction or validation fails, clean up uploaded file
                logger.error(f"ZIP extraction/validation failed, cleaning up: {stored_path}", exc_info=True)
                try:
                    if stored_path and self.storage.file_exists(stored_path):
                        os.remove(self.storage.get_file_path(stored_path))
                        logger.info(f"Cleaned up uploaded file: {stored_path}")
                except Exception as cleanup_error:
                    logger.error(f"Error cleaning up file: {cleanup_error}", exc_info=True)
                raise
                
        except Exception as e:
            logger.error(f"Error in create_from_zip: {e}", exc_info=True)
            raise
    
    async def create_from_github(
        self,
        name: str,
        github_url: str,
        owner_id: int,
        personas: List[str],
        config: Optional[Dict[str, Any]] = None
    ) -> Project:
        """Create project from GitHub URL"""
        logger.info(f"Creating project from GitHub: {name} (URL: {github_url}, owner: {owner_id})")
        
        # Validate GitHub URL
        if not self._validate_github_url(github_url):
            logger.error(f"Invalid GitHub URL format: {github_url}")
            raise GitHubAccessException("Invalid GitHub URL format")
        
        logger.debug("GitHub URL validation passed")
        
        # TODO: In future milestones, clone the repository
        # For M1, just store the URL
        
        try:
            project = Project(
                name=name,
                owner_id=owner_id,
                source_type=SourceType.GITHUB,
                source_path=github_url,
                status=ProjectStatus.CREATED,
                personas=personas,
                config=config or {}
            )
            
            self.db.add(project)
            await self.db.commit()
            await self.db.refresh(project)
            
            logger.info(f"GitHub project created successfully: {project.name} (ID: {project.id})")
            return project
        except Exception as e:
            logger.error(f"Error creating GitHub project: {e}", exc_info=True)
            raise
    
    async def clone_github_repo(self, project_id: str, github_url: str) -> str:
        """
        Clone a GitHub repository to the project's extracted directory
        
        Args:
            project_id: UUID of the project
            github_url: GitHub repository URL
            
        Returns:
            Path to extracted repository
        """
        logger.info(f"Cloning GitHub repository: {github_url} for project {project_id}")
        
        try:
            # Create target directory for cloned repo
            target_dir = storage_service.projects_path / str(project_id) / "extracted"
            
            # Remove if already exists (in case of retry)
            if target_dir.exists():
                logger.debug(f"Removing existing directory: {target_dir}")
                shutil.rmtree(target_dir)
            
            # Create parent directory
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # Clone the repository using git
            logger.debug(f"Running git clone to {target_dir}")
            try:
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", github_url, str(target_dir)],
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout
                    logger.error(f"Git clone failed: {error_msg}")
                    raise GitHubAccessException(f"Failed to clone repository: {error_msg}")
                    
            except FileNotFoundError:
                logger.error("Git is not installed or not in PATH")
                raise GitHubAccessException(
                    "Git is required to clone repositories. Please install Git and ensure it's in your PATH."
                )
            except subprocess.TimeoutExpired:
                logger.error("Git clone timed out after 5 minutes")
                raise GitHubAccessException("Repository cloning timed out. Repository may be too large.")
            
            # Verify the clone was successful
            if not target_dir.exists():
                raise GitHubAccessException("Repository clone failed - directory not created")
            
            # Count files to verify something was cloned
            file_count = len(list(target_dir.rglob("*")))
            if file_count == 0:
                raise GitHubAccessException("Repository appears to be empty")
            
            logger.info(f"Successfully cloned repository with {file_count} files/directories")
            
            # Return relative path for storage
            relative_path = f"projects/{str(project_id)}/extracted"
            return relative_path
            
        except GitHubAccessException:
            raise
        except Exception as e:
            logger.error(f"Error cloning GitHub repository: {e}", exc_info=True)
            raise GitHubAccessException(f"Failed to clone repository: {str(e)}")
    
    async def _validate_zip_file(self, file: UploadFile):
        """Validate uploaded ZIP file"""
        logger.debug(f"Validating ZIP file: {file.filename}")
        
        # Check file extension
        if not file.filename:
            logger.error("ZIP validation failed: Filename is required")
            raise InvalidFileException("Filename is required")
        
        filename_lower = file.filename.lower()
        if not (filename_lower.endswith('.zip')):
            logger.warning(f"ZIP validation failed: Unsupported file type - {file.filename}")
            raise UnsupportedFileTypeException(
                f"Unsupported file type. Only ZIP files are supported. Got: {file.filename}"
            )
        
        # Check file size
        content = await file.read()
        file_size_mb = len(content) / (1024 * 1024)
        logger.debug(f"ZIP file size: {file_size_mb:.2f} MB")
        
        if file_size_mb > settings.MAX_ZIP_SIZE_MB:
            logger.warning(f"ZIP validation failed: File too large - {file_size_mb:.2f} MB > {settings.MAX_ZIP_SIZE_MB} MB")
            raise FileTooLargeException(
                f"File size ({file_size_mb:.2f} MB) exceeds maximum allowed size "
                f"({settings.MAX_ZIP_SIZE_MB} MB)"
            )
        
        # Reset file pointer for later use
        await file.seek(0)
        
        # Validate ZIP structure
        try:
            # Read into memory for validation
            await file.seek(0)
            content = await file.read()
            await file.seek(0)
            
            # Try to open as ZIP
            import io
            zip_file = zipfile.ZipFile(io.BytesIO(content), 'r')
            zip_file.testzip()  # Test for corruption
            zip_file.close()
        except zipfile.BadZipFile:
            raise CorruptedFileException("File is not a valid ZIP archive or is corrupted")
        except Exception as e:
            raise CorruptedFileException(f"Error reading ZIP file: {str(e)}")
    
    def _validate_extracted_repository(self, extracted_path: str):
        """Validate that extracted repository contains code"""
        logger.debug(f"Validating extracted repository: {extracted_path}")
        extract_dir = storage_service.get_file_path(extracted_path)
        
        if not extract_dir.exists():
            logger.error(f"Repository validation failed: Extracted directory does not exist - {extracted_path}")
            raise EmptyRepositoryException("Extracted directory does not exist")
        
        # Look for common code file patterns
        code_extensions = {
            '.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.cs', '.go', '.rs',
            '.rb', '.php', '.swift', '.kt', '.scala', '.r', '.m', '.sh', '.sql',
            '.html', '.css', '.jsx', '.tsx', '.vue', '.json', '.yaml', '.yml',
            '.xml', '.toml', '.ini', '.cfg', '.conf'
        }
        
        # Skip common non-code directories
        skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env', '.env'}
        
        code_files_found = []
        
        for root, dirs, files in os.walk(extract_dir):
            # Filter out skip directories
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() in code_extensions:
                    code_files_found.append(str(file_path.relative_to(extract_dir)))
        
        logger.debug(f"Found {len(code_files_found)} code files in repository")
        
        if not code_files_found:
            logger.warning("Repository validation failed: No recognizable code files found")
            raise EmptyRepositoryException(
                "Repository contains no recognizable code files. "
                "Please ensure the ZIP contains source code files."
            )
    
    def _validate_github_url(self, url: str) -> bool:
        """Validate GitHub URL format"""
        # GitHub URL pattern - better validation
        # Usernames: alphanumeric, hyphens, no dots
        # Repository: alphanumeric, hyphens, underscores, dots
        pattern = r'^https?://(www\.)?github\.com/[\w\-]+/[\w\.\-]+(/.*)?$'
        is_valid = bool(re.match(pattern, url))
        
        if not is_valid:
            logger.warning(f"Invalid GitHub URL format: {url}")
        
        return is_valid
    
    async def get_project(self, project_id: int, owner_id: int) -> Optional[Project]:
        """Get project by ID, ensuring ownership"""
        result = await self.db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.owner_id == owner_id
            )
        )
        return result.scalar_one_or_none()
