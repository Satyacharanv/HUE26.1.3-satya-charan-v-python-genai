"""Project model"""
from sqlalchemy import Column, String, ForeignKey, Enum, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
import uuid
from src.models.base import BaseModel


class SourceType(str, enum.Enum):
    """Source type enumeration"""
    ZIP = "zip"
    GITHUB = "github"


class ProjectStatus(str, enum.Enum):
    """Project status enumeration"""
    CREATED = "created"
    PREPROCESSING = "preprocessing"
    ANALYZING = "analyzing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class PersonaType(str, enum.Enum):
    """Persona type enumeration"""
    SDE = "sde"
    PM = "pm"


class Project(BaseModel):
    """Project model"""
    __tablename__ = "projects"
    
    name = Column(String(255), nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    source_type = Column(Enum(SourceType), nullable=False)
    source_path = Column(Text, nullable=False)  # GitHub URL or file path
    status = Column(Enum(ProjectStatus), default=ProjectStatus.CREATED, nullable=False)
    personas = Column(JSON, nullable=False)  # List of PersonaType values
    config = Column(JSON, default={}, nullable=True)  # Analysis configuration
    
    # Relationships
    owner = relationship("User", backref="projects")
    
    def __repr__(self):
        return f"<Project(id={self.id}, name={self.name}, status={self.status})>"
