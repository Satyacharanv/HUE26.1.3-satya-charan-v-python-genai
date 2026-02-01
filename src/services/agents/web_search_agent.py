"""Web-augmented analysis agent."""
from typing import Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.services.agents.base_agent import BaseAgent
from src.services.analysis_progress import AnalysisProgressService
from src.services.langfuse_client import log_generation
from src.services.mcp_client import call_mcp_web_search
from src.services.usage_tracker import record_llm_usage


def _format_web_findings(payload: Dict[str, Any]) -> str:
    """Turn normalized web search result into user-facing markdown. Never return raw JSON or tool repr."""
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    message = (payload.get("message") or "").strip()
    query = (payload.get("query") or "").strip()

    if results:
        lines = ["**Web Research Findings**", ""]
        if query:
            lines.append(f"*Query:* {query}")
            lines.append("")
        for i, item in enumerate(results[:10], 1):
            if not isinstance(item, dict):
                continue
            title = item.get("title") or "Untitled"
            link = item.get("link") or ""
            snippet = item.get("snippet") or ""
            lines.append(f"{i}. **[{title}]({link})**" if link else f"{i}. **{title}**")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")
        return "\n".join(lines).strip()

    if message:
        return (
            "**Web Research**\n\n"
            "Web search was not available for this analysis. "
            f"{message}. No external references could be added."
        )
    return (
        "**Web Research**\n\n"
        "Web search was not available for this analysis. No external references could be added."
    )


class WebSearchAgent(BaseAgent):
    """Fetches latest best practices from the web using OpenAI web search."""

    name = "web_search"
    description = "Search latest best practices online"

    async def run(
        self,
        state: Dict[str, Any],
        db: AsyncSession,
        progress: AnalysisProgressService
    ) -> Dict[str, Any]:
        options = state.get("analysis_options", {}) or {}
        if not options.get("enable_web_search", True):
            await progress.log_event(
                analysis_id=state["analysis_id"],
                level="info",
                message="WebSearchAgent: web search disabled by configuration",
                stage="agent_orchestration"
            )
            return {"web_findings": "Web search disabled by configuration."}

        gaps = state.get("knowledge_gaps", []) or []
        requester = state.get("web_search_requester") or "structure"
        if not gaps:
            await progress.log_event(
                analysis_id=state["analysis_id"],
                level="info",
                message=f"WebSearchAgent: no knowledge gaps detected - skipping web search (requested_by={requester})",
                stage="agent_orchestration"
            )
            return {"web_findings": "No knowledge gaps detected. Web search skipped."}

        repo_summary = state.get("repo_summary", {})
        framework = repo_summary.get("primary_framework") or repo_summary.get("repository_type", "software")

        await progress.log_event(
            analysis_id=state["analysis_id"],
            level="info",
            message=f"WebSearchAgent: searching latest best practices for {framework} (requested_by={requester})",
            stage="agent_orchestration"
        )

        query = (
            f"Latest best practices for {framework} APIs, security, and deployment. "
            f"Focus on these gaps: {', '.join(gaps)}. "
            "Provide concise bullet points with references."
        )

        try:
            mcp_result = await call_mcp_web_search(query, limit=5)
            if mcp_result is not None:
                await progress.log_event(
                    analysis_id=state["analysis_id"],
                    level="info",
                    message=f"WebSearchAgent: MCP web search completed (requested_by={requester})",
                    stage="agent_orchestration"
                )
                findings_text = _format_web_findings(mcp_result)
                return {"web_findings": findings_text}

            if not settings.OPENAI_API_KEY:
                await progress.log_event(
                    analysis_id=state["analysis_id"],
                    level="warning",
                    message=f"WebSearchAgent: OpenAI API key not configured - skipping web search (requested_by={requester})",
                    stage="agent_orchestration"
                )
                return {"web_findings": "OpenAI API key not configured. Web search skipped."}

            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

            try:
                response = await client.responses.create(
                    model=settings.OPENAI_MODEL,
                    input=query,
                    tools=[{"type": "web_search"}],
                )
                findings = getattr(response, "output_text", None)
                if not findings:
                    findings = str(response)
            except Exception:
                # Fallback to a regular completion if web tools are unavailable
                chat = await client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[{"role": "user", "content": query}]
                )
                findings = chat.choices[0].message.content
                response = chat

            usage = {}
            if getattr(response, "usage", None):
                usage = {
                    "input": response.usage.prompt_tokens,
                    "output": response.usage.completion_tokens,
                    "total": response.usage.total_tokens,
                }
                await record_llm_usage(
                    progress,
                    state["analysis_id"],
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                    settings.OPENAI_MODEL,
                )
            log_generation(
                name="web_search",
                model=settings.OPENAI_MODEL,
                input_data=query,
                output_data=findings,
                usage=usage,
                metadata={
                    "analysis_id": str(state.get("analysis_id")),
                    "requested_by": requester,
                },
            )

            await progress.log_event(
                analysis_id=state["analysis_id"],
                level="info",
                message=f"WebSearchAgent: web research completed (requested_by={requester})",
                stage="agent_orchestration"
            )

            return {"web_findings": findings}

        except Exception as e:
            await progress.log_event(
                analysis_id=state["analysis_id"],
                level="warning",
                message=f"WebSearchAgent: failed to fetch web data ({str(e)[:120]})",
                stage="agent_orchestration"
            )
            return {"web_findings": "Web search failed; see logs for details."}
