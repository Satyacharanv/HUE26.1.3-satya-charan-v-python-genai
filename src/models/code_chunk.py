"""Code chunk model for storing parsed code segments"""
from sqlalchemy import Column, String, Text, Integer, ForeignKey, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship
import enum
from src.models.base import BaseModel


class ChunkType(str, enum.Enum):
    """Type of code chunk"""
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    MODULE = "module"
    CONSTANT = "constant"
    INTERFACE = "interface"
    ENUM = "enum"
    DECORATOR = "decorator"
    UNKNOWN = "unknown"


class CodeChunk(BaseModel):
    """Code chunk model - stores parsed code segments with metadata"""
    __tablename__ = "code_chunks"
    
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)  # Relative path in project
    chunk_type = Column(String(50), nullable=False)  # Function, Class, Method, etc.
    name = Column(String(255), nullable=False)  # Function/class name
    
    # Content
    content = Column(Text, nullable=False)  # Actual code content
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    
    # Metadata
    language = Column(String(50), nullable=False)  # Python, JavaScript, Java, etc.
    parent_chunk_id = Column(UUID(as_uuid=True), ForeignKey("code_chunks.id"), nullable=True)  # For nested chunks
    
    # Semantic search
    embedding = Column(Vector(1536), nullable=True)  # Vector embedding (pgvector) - 1536 dimensions for text-embedding-3-small
    embedding_model = Column(String(100), nullable=True)  # Model used for embedding
    
    # Additional metadata
    is_important = Column(Boolean, default=False)  # Entry point, config, etc.
    docstring = Column(Text, nullable=True)  # Docstring/comments
    dependencies = Column(JSONB, default={}, nullable=True)  # External dependencies used
    parameters = Column(JSONB, default={}, nullable=True)  # Function parameters
    return_type = Column(String(255), nullable=True)  # Return type
    
    # Relationships
    project = relationship("Project", backref="code_chunks")
    children = relationship(
        "CodeChunk",
        remote_side="[CodeChunk.id]",
        backref="parent",
        foreign_keys=[parent_chunk_id]
    )
    
    def __repr__(self):
        return f"<CodeChunk(id={self.id}, name={self.name}, type={self.chunk_type}, file={self.file_path})>"
