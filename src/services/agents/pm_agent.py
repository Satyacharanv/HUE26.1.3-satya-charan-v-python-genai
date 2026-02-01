"""PM documentation agent."""
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.analysis_progress import AnalysisProgressService
from src.services.agents.base_agent import BaseAgent
from src.services.agents.report_llm import generate_pm_report


class PMAgent(BaseAgent):
    """Generates business summary for PM persona (LLM when available, else template)."""

    name = "pm"
    description = "Generate PM-focused documentation notes"

    async def run(
        self,
        state: Dict[str, Any],
        db: AsyncSession,
        progress: AnalysisProgressService
    ) -> Dict[str, Any]:
        if not state.get("run_pm", True):
            await progress.log_event(
                analysis_id=state["analysis_id"],
                level="info",
                message="PMAgent: skipped (persona not selected)",
                stage="documentation_generation"
            )
            return {}

        await progress.log_event(
            analysis_id=state["analysis_id"],
            level="info",
            message="PMAgent: compiling business summary",
            stage="documentation_generation"
        )

        repo = state.get("repo_summary", {})
        depth = state.get("analysis_depth", "standard")
        options = state.get("analysis_options", {}) or {}
        instructions = options.get("instructions", []) or []
        instruction_lines = []
        for item in instructions:
            text = item.get("text") if isinstance(item, dict) else str(item)
            scope = item.get("scope", "global") if isinstance(item, dict) else "global"
            if text:
                instruction_lines.append(f"- ({scope}) {text}")
        instruction_block = "\n".join(instruction_lines) if instruction_lines else "none"

        output = await generate_pm_report(
            repo, instruction_block, depth,
            progress=progress,
            analysis_id=state["analysis_id"],
        )
        if not output:
            output = (
                f"PM Summary (depth={depth}):\n"
                f"- Product foundation: {repo.get('repository_type')} project\n"
                f"- Key framework: {repo.get('primary_framework')}\n"
                f"- Entry points: {list(repo.get('entry_points', {}).values())}\n"
                f"- Scope estimate: {repo.get('code_files')} code files\n"
                f"- User context:\n{instruction_block}"
            )

        await progress.log_event(
            analysis_id=state["analysis_id"],
            level="milestone",
            message="PMAgent: business summary generated",
            stage="documentation_generation"
        )
        await progress.log_event(
            analysis_id=state["analysis_id"],
            level="info",
            message=output[:500] + ("..." if len(output) > 500 else ""),
            stage="documentation_generation"
        )

        return {"pm_output": output}
