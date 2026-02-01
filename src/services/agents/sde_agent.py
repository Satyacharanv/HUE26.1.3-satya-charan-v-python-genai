"""SDE documentation agent."""
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.analysis_progress import AnalysisProgressService
from src.services.agents.base_agent import BaseAgent
from src.services.agents.report_llm import generate_sde_report_structured, sde_structured_to_markdown


class SDEAgent(BaseAgent):
    """Generates technical summary for SDE persona (LLM when available, else template)."""

    name = "sde"
    description = "Generate SDE-focused documentation notes"

    async def run(
        self,
        state: Dict[str, Any],
        db: AsyncSession,
        progress: AnalysisProgressService
    ) -> Dict[str, Any]:
        await progress.log_event(
            analysis_id=state["analysis_id"],
            level="info",
            message="SDEAgent: compiling technical summary",
            stage="documentation_generation"
        )

        repo = state.get("repo_summary", {})
        web = state.get("web_findings", "") or ""
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

        structured = await generate_sde_report_structured(
            repo, web, instruction_block, depth,
            progress=progress,
            analysis_id=state["analysis_id"],
        )
        output = sde_structured_to_markdown(structured) if structured else ""
        if not output:
            output = (
                f"SDE Summary (depth={depth}):\n"
                f"- Repo type: {repo.get('repository_type')}\n"
                f"- Framework: {repo.get('primary_framework')}\n"
                f"- Code files: {repo.get('code_files')}\n"
                f"- Entry points: {list(repo.get('entry_points', {}).values())}\n"
                f"- API hints: {repo.get('api_chunk_hits')}\n"
                f"- Web notes: {web[:600] if web else 'none'}\n"
                f"- User context:\n{instruction_block}"
            )

        await progress.log_event(
            analysis_id=state["analysis_id"],
            level="milestone",
            message="SDEAgent: technical summary generated",
            stage="documentation_generation"
        )
        await progress.log_event(
            analysis_id=state["analysis_id"],
            level="info",
            message=output[:500] + ("..." if len(output) > 500 else ""),
            stage="documentation_generation"
        )

        return {"sde_output": output, "sde_structured": structured}
