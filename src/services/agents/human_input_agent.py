"""Human-in-the-loop input agent."""
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.types import interrupt
from src.services.analysis_progress import AnalysisProgressService
from src.services.agents.base_agent import BaseAgent
from src.models.analysis import AnalysisStatus


class HumanInputAgent(BaseAgent):
    """Injects user context updates during orchestration."""

    name = "human_input"
    description = "Pause for human guidance before documentation"

    async def run(
        self,
        state: Dict[str, Any],
        db: AsyncSession,
        progress: AnalysisProgressService
    ) -> Dict[str, Any]:
        analysis = await progress.get_analysis(state["analysis_id"])
        if analysis and analysis.status in {AnalysisStatus.COMPLETED, AnalysisStatus.FAILED, AnalysisStatus.CANCELLED}:
            return {}
        options = (analysis.user_context or {}) if analysis else (state.get("analysis_options", {}) or {})
        instructions = list(options.get("instructions", []) or [])
        pending_context = bool(options.get("pending_context"))

        if not pending_context:
            return {"analysis_options": options}

        latest = instructions[-1] if instructions else {}
        prompt = {
            "type": "context_update",
            "resume_with": {
                "text": latest.get("text", ""),
                "scope": latest.get("scope", "global")
            }
        }

        response = interrupt(prompt)
        resume_text = ""
        resume_scope = "global"
        if isinstance(response, dict):
            resume_text = response.get("text") or response.get("instruction") or response.get("content") or ""
            resume_scope = response.get("scope") or "global"
        elif response is not None:
            resume_text = str(response).strip()

        if resume_text:
            latest_text = latest.get("text", "").strip()
            if resume_text != latest_text:
                instructions.append({"text": resume_text, "scope": resume_scope})

        updated_options = dict(options)
        updated_options["instructions"] = instructions
        updated_options["pending_context"] = False

        if analysis:
            analysis.user_context = updated_options
            await db.commit()
            try:
                await progress.log_event(
                    analysis_id=state["analysis_id"],
                    level="info",
                    message=f"Context applied to agents: {resume_text[:200]}",
                    stage="agent_orchestration"
                )
            except Exception:
                pass

        return {"analysis_options": updated_options}
