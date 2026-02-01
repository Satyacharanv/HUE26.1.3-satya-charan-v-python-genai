"""Base agent interface for analysis orchestration."""
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.analysis_progress import AnalysisProgressService


class BaseAgent:
    """Base class for specialized analysis agents."""

    name: str = "base"
    description: str = "Base agent"

    async def run(
        self,
        state: Dict[str, Any],
        db: AsyncSession,
        progress: AnalysisProgressService
    ) -> Dict[str, Any]:
        """Run agent and return updated state."""
        raise NotImplementedError("Agent must implement run()")
