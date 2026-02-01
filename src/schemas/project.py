"""Project schemas"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from src.models.project import ProjectStatus, SourceType, PersonaType


class ProjectCreate(BaseModel):
    """Project creation request"""
    name: str = Field(..., min_length=1, max_length=255)
    source_type: SourceType
    source_path: str  # GitHub URL or will be set by server for ZIP
    personas: List[PersonaType] = Field(..., min_items=1)
    config: Optional[Dict[str, Any]] = None


class ProjectResponse(BaseModel):
    """Project response"""
    id: UUID
    name: str
    owner_id: UUID
    source_type: SourceType
    source_path: str
    status: ProjectStatus
    personas: List[str]
    config: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    """List of projects response"""
    projects: List[ProjectResponse]
    total: int
