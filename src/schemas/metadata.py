"""Schemas for M2 models (code chunks and repository metadata)"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID


class CodeChunkResponse(BaseModel):
    """Code chunk response"""
    id: UUID
    project_id: UUID
    file_path: str
    chunk_type: str
    name: str
    content: str
    start_line: int
    end_line: int
    language: str
    parent_chunk_id: Optional[UUID] = None
    is_important: bool = False
    docstring: Optional[str] = None
    dependencies: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    return_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CodeChunkListResponse(BaseModel):
    """List of code chunks"""
    chunks: List[CodeChunkResponse]
    total: int
    project_id: UUID


class RepositoryMetadataResponse(BaseModel):
    """Repository metadata response"""
    id: UUID
    project_id: UUID
    repository_type: str
    primary_framework: Optional[str] = None
    secondary_frameworks: Optional[List[str]] = None
    total_files: int
    code_files: int
    test_files: int
    config_files: int
    documentation_files: int
    entry_points: Optional[Dict[str, Any]] = None
    config_files_list: Optional[List[str]] = None
    dependencies: Optional[Dict[str, Any]] = None
    is_preprocessed: bool
    preprocessing_status: str
    preprocessing_error: Optional[str] = None
    file_count_processed: int
    total_chunks_created: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class FileMetadataResponse(BaseModel):
    """File metadata response"""
    id: UUID
    project_id: UUID
    repository_id: UUID
    file_path: str
    file_name: str
    file_type: str
    language: Optional[str] = None
    lines_of_code: int
    is_test_file: bool
    is_important: bool
    has_docstring: bool
    function_count: int
    class_count: int
    imports: Optional[Dict[str, Any]] = None
    is_processed: bool
    chunks_created: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class FileMetadataListResponse(BaseModel):
    """List of file metadata"""
    files: List[FileMetadataResponse]
    total: int
    project_id: UUID


class RepositoryIntelligenceResponse(BaseModel):
    """Complete repository intelligence summary"""
    repository_metadata: RepositoryMetadataResponse
    files: List[FileMetadataResponse]
    important_files: List[FileMetadataResponse]
    code_chunks_summary: Dict[str, Any]  # Count by type, language, etc.
