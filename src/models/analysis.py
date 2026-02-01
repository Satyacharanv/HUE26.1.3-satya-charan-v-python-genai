"""Analysis progress tracking models"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
from src.models.base import BaseModel


class AnalysisStatus(str, enum.Enum):
    """Status of analysis"""
    PENDING = "pending"  # Waiting to start
    PREPROCESSING = "preprocessing"  # Scanning repo structure
    ANALYZING = "analyzing"  # Running agents
    PAUSED = "paused"  # User paused analysis
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"  # Error occurred
    CANCELLED = "cancelled"  # User cancelled


class AnalysisStage(str, enum.Enum):
    """High-level analysis stages"""
    REPO_SCAN = "repo_scan"  # Initial file scanning
    CODE_CHUNKING = "code_chunking"  # Breaking code into chunks
    EMBEDDING_GENERATION = "embedding_generation"  # Generating embeddings
    AGENT_ORCHESTRATION = "agent_orchestration"  # Running agents
    DOCUMENTATION_GENERATION = "documentation_generation"  # Creating final docs
    COMPLETED = "completed"


class Analysis(BaseModel):
    """Analysis job tracking"""
    __tablename__ = "analyses"
    
    project_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # FK to projects
    status = Column(SQLEnum(AnalysisStatus), default=AnalysisStatus.PENDING, nullable=False)
    current_stage = Column(SQLEnum(AnalysisStage), nullable=True)
    
    # Progress tracking
    total_files = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    processed_chunks = Column(Integer, default=0)
    
    # Token tracking
    total_tokens_used = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0.0)  # USD
    
    # Configuration
    analysis_depth = Column(String(50), default="standard")  # quick, standard, deep
    target_personas = Column(JSONB, default={})  # {"sde": true, "pm": true}
    verbosity_level = Column(String(50), default="normal")  # low, normal, high
    
    # Timing
    started_at = Column(DateTime, nullable=True)
    paused_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # State management
    paused = Column(Boolean, default=False)
    user_context = Column(JSONB, default={})  # User-provided context/instructions
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<Analysis(id={self.id}, project_id={self.project_id}, status={self.status})>"


class AnalysisLog(BaseModel):
    """High-frequency analysis events (persistent log)"""
    __tablename__ = "analysis_logs"
    
    analysis_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # FK to analyses
    
    # Log level
    level = Column(String(20), nullable=False)  # info, warning, error, milestone
    
    # Message
    message = Column(Text, nullable=False)
    
    # Context data
    stage = Column(String(100), nullable=True)
    current_file = Column(String(500), nullable=True)
    file_index = Column(Integer, nullable=True)
    total_files = Column(Integer, nullable=True)
    
    # Progress percentage
    progress_percentage = Column(Float, nullable=True)
    
    # Timestamp (auto-set by database)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<AnalysisLog(id={self.id}, level={self.level}, message={self.message[:50]}...)>"


class AnalysisArtifact(BaseModel):
    """Final generated artifacts"""
    __tablename__ = "analysis_artifacts"
    
    analysis_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Artifact type
    artifact_type = Column(String(50), nullable=False)  # sde_report, pm_report, diagrams
    persona = Column(String(50), nullable=True)  # sde, pm
    
    # Content
    content = Column(Text, nullable=False)  # Markdown or JSON
    format = Column(String(50), default="markdown")  # markdown, json, html
    
    # Metadata
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<AnalysisArtifact(id={self.id}, type={self.artifact_type})>"


class AnalysisInteraction(BaseModel):
    """User interactions during analysis (questions, context, etc.)."""
    __tablename__ = "analysis_interactions"

    analysis_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Interaction metadata
    kind = Column(String(20), nullable=False)  # question, context, system
    scope = Column(String(200), nullable=True)  # global, module name, etc.

    # Content
    content = Column(Text, nullable=False)
    response = Column(Text, nullable=True)

    # Timestamp (auto-set by database)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AnalysisInteraction(id={self.id}, kind={self.kind})>"
