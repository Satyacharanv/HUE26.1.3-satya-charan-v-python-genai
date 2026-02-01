"""Coordinator agent for routing based on personas."""
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.analysis_progress import AnalysisProgressService
from src.services.agents.base_agent import BaseAgent


class CoordinatorAgent(BaseAgent):
    """Determines which downstream agents should run."""

    name = "coordinator"
    description = "Route analysis based on target personas"

    async def run(
        self,
        state: Dict[str, Any],
        db: AsyncSession,
        progress: AnalysisProgressService
    ) -> Dict[str, Any]:
        target_personas = state.get("target_personas", {}) or {}
        run_sde = bool(target_personas.get("sde", False))
        run_pm = bool(target_personas.get("pm", False))

        await progress.log_event(
            analysis_id=state["analysis_id"],
            level="info",
            message=f"Coordinator: routing agents (sde={run_sde}, pm={run_pm})",
            stage="agent_orchestration"
        )

        return {
            "run_sde": run_sde,
            "run_pm": run_pm
        }
