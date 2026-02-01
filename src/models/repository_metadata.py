"""Repository and file metadata models"""
from sqlalchemy import Column, String, Text, Integer, ForeignKey, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.models.base import BaseModel


class RepositoryMetadata(BaseModel):
    """Repository-level metadata and intelligence"""
    __tablename__ = "repository_metadata"
    
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), unique=True, nullable=False, index=True)
    
    # Repository intelligence
    repository_type = Column(String(100), nullable=False)  # Python, JavaScript, Java, Go, etc.
    primary_framework = Column(String(100), nullable=True)  # FastAPI, Django, Spring, etc.
    secondary_frameworks = Column(JSONB, default=[], nullable=True)  # List of other frameworks
    
    # File statistics
    total_files = Column(Integer, default=0)
    code_files = Column(Integer, default=0)
    test_files = Column(Integer, default=0)
    config_files = Column(Integer, default=0)
    documentation_files = Column(Integer, default=0)
    
    # Entry points and important files
    entry_points = Column(JSONB, default={}, nullable=True)  # main.py, index.js, etc.
    config_files_list = Column(JSONB, default=[], nullable=True)  # package.json, requirements.txt, etc.
    
    # Dependencies
    dependencies = Column(JSONB, default={}, nullable=True)  # Framework & library versions
    
    # Analysis state
    is_preprocessed = Column(Boolean, default=False)
    preprocessing_status = Column(String(50), default="pending")  # pending, processing, completed, failed
    preprocessing_error = Column(Text, nullable=True)
    file_count_processed = Column(Integer, default=0)
    total_chunks_created = Column(Integer, default=0)
    
    # Relationships
    project = relationship("Project", backref="repository_metadata", uselist=False)
    files = relationship("FileMetadata", backref="repository", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<RepositoryMetadata(project_id={self.project_id}, type={self.repository_type})>"


class FileMetadata(BaseModel):
    """File-level metadata"""
    __tablename__ = "file_metadata"
    
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("repository_metadata.id"), nullable=False, index=True)
    
    # File information
    file_path = Column(String(500), nullable=False)  # Relative path in project
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # code, config, test, doc, binary
    language = Column(String(50), nullable=True)  # Python, JavaScript, etc.
    
    # File statistics
    lines_of_code = Column(Integer, default=0)
    is_test_file = Column(Boolean, default=False)
    is_important = Column(Boolean, default=False)  # Entry point, config, requirement file
    
    # Content analysis
    has_docstring = Column(Boolean, default=False)
    function_count = Column(Integer, default=0)
    class_count = Column(Integer, default=0)
    imports = Column(JSONB, default={}, nullable=True)  # External imports/dependencies
    
    # Processing state
    is_processed = Column(Boolean, default=False)
    chunks_created = Column(Integer, default=0)
    
    # Relationships
    project = relationship("Project")
    
    def __repr__(self):
        return f"<FileMetadata(file_path={self.file_path}, language={self.language})>"
