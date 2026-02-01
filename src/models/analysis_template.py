"""Analysis template model"""
from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.models.base import BaseModel


class AnalysisTemplate(BaseModel):
    """Reusable analysis configuration templates"""
    __tablename__ = "analysis_templates"

    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    config = Column(JSONB, default={}, nullable=False)

    def __repr__(self):
        return f"<AnalysisTemplate(id={self.id}, name={self.name})>"
