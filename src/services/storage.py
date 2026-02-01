"""File storage service - abstracted for easy cloud migration"""
import os
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO, Optional
from src.core.config import settings
from src.core.logging_config import get_logger
from src.core.exceptions import InvalidFileException, CorruptedFileException

logger = get_logger(__name__)


class StorageService:
    """Storage service with local implementation, designed for easy cloud migration"""
    
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or settings.STORAGE_PATH)
        self.projects_path = self.base_path / "projects"
        self.uploads_path = self.base_path / "uploads"
        
        # Ensure directories exist
        self.projects_path.mkdir(parents=True, exist_ok=True)
        self.uploads_path.mkdir(parents=True, exist_ok=True)
    
    def save_upload(self, file_content: bytes, filename: str) -> str:
        """Save uploaded file and return relative path"""
        try:
            file_ext = Path(filename).suffix
            unique_filename = f"{uuid.uuid4()}{file_ext}"
            file_path = self.uploads_path / unique_filename
            
            logger.debug(f"Saving upload: {filename} -> {unique_filename}")
            
            # Write file
            with open(file_path, "wb") as f:
                f.write(file_content)
            
            logger.info(f"File saved successfully: {unique_filename} ({len(file_content)} bytes)")
            # Return relative path for storage in DB
            return str(file_path.relative_to(self.base_path))
            
        except IOError as e:
            logger.error(f"I/O error while saving file: {e}", exc_info=True)
            raise InvalidFileException(f"Failed to save file: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error while saving file: {e}", exc_info=True)
            raise
    
    def save_project_file(self, project_id: int, filename: str, content: bytes) -> str:
        """Save project-specific file"""
        try:
            project_dir = self.projects_path / str(project_id)
            project_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = project_dir / filename
            logger.debug(f"Saving project file for project {project_id}: {filename}")
            
            with open(file_path, "wb") as f:
                f.write(content)
            
            logger.info(f"Project file saved: {file_path}")
            return str(file_path.relative_to(self.base_path))
            
        except IOError as e:
            logger.error(f"I/O error while saving project file: {e}", exc_info=True)
            raise InvalidFileException(f"Failed to save project file: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error while saving project file: {e}", exc_info=True)
            raise
    
    def get_file_path(self, relative_path: str) -> Path:
        """Get absolute path from relative path"""
        return self.base_path / relative_path
    
    def extract_zip(self, zip_path: str, project_id: int) -> str:
        """Extract ZIP file to project directory"""
        logger.info(f"Extracting ZIP to project {project_id}: {zip_path}")
        
        try:
            zip_file_path = self.get_file_path(zip_path)
            
            if not zip_file_path.exists():
                logger.error(f"ZIP file does not exist: {zip_path}")
                raise FileNotFoundError(f"ZIP file not found: {zip_path}")
            
            extract_dir = self.projects_path / str(project_id) / "extracted"
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            logger.info(f"ZIP extraction successful: {extract_dir}")
            return str(extract_dir.relative_to(self.base_path))
            
        except zipfile.BadZipFile as e:
            logger.error(f"Corrupted ZIP file during extraction: {zip_path}", exc_info=True)
            raise CorruptedFileException("ZIP file is corrupted and cannot be extracted")
        except OSError as e:
            logger.error(f"File system error during extraction: {e}", exc_info=True)
            raise InvalidFileException(f"File system error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during ZIP extraction: {e}", exc_info=True)
            raise
    
    def delete_project_files(self, project_id: int):
        """Delete all files for a project"""
        project_dir = self.projects_path / str(project_id)
        if project_dir.exists():
            shutil.rmtree(project_dir)
    
    def file_exists(self, relative_path: str) -> bool:
        """Check if file exists"""
        return self.get_file_path(relative_path).exists()
    
    def get_file_size(self, relative_path: str) -> int:
        """Get file size in bytes"""
        return self.get_file_path(relative_path).stat().st_size


# Global storage service instance
storage_service = StorageService()
