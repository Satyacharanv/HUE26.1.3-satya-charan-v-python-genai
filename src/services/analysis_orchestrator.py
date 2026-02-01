"""LangGraph-based analysis orchestrator."""
import json
import os
from typing import Dict, Any, TypedDict
from uuid import UUID
from langgraph.graph import StateGraph, END
from langgraph.types import Command
try:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    AsyncSqliteSaver = None  # type: ignore[assignment]
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.services.analysis_progress import AnalysisProgressService
from src.models.analysis import AnalysisStage
from src.services.agents import (
    CoordinatorAgent,
    StructureAgent,
    WebSearchAgent,
    HumanInputAgent,
    SDEAgent,
    PMAgent
)


class AnalysisState(TypedDict, total=False):
    analysis_id: UUID
    project_id: UUID
    analysis_depth: str
    verbosity_level: str
    target_personas: Dict[str, Any]
    analysis_options: Dict[str, Any]
    repo_summary: Dict[str, Any]
    web_findings: str
    sde_output: str
    pm_output: str
    run_sde: bool
    run_pm: bool
    knowledge_gaps: list[str]
    sde_structured: dict


class AnalysisOrchestrator:
    """Runs a LangGraph pipeline across specialized agents."""

    def __init__(self, db: AsyncSession, progress: AnalysisProgressService):
        self.db = db
        self.progress = progress
        self.coordinator = CoordinatorAgent()
        self.structure = StructureAgent()
        self.web_search = WebSearchAgent()
        self.human_input = HumanInputAgent()
        self.sde_agent = SDEAgent()
        self.pm_agent = PMAgent()
        self._checkpointer = None
        self._checkpoint_conn = None

    async def _get_checkpointer(self):
        if self._checkpointer is None:
            if AsyncSqliteSaver is not None:
                checkpoint_path = os.path.join(settings.STORAGE_PATH, "langgraph_checkpoints.sqlite")
                try:
                    import aiosqlite
                    connection = await aiosqlite.connect(checkpoint_path)
                    self._checkpoint_conn = connection
                    self._checkpointer = AsyncSqliteSaver(connection)
                except Exception:
                    self._checkpointer = MemorySaver()
            else:
                self._checkpointer = MemorySaver()
        return self._checkpointer

    async def close(self) -> None:
        """Close any open checkpoint connections."""
        if self._checkpoint_conn is not None:
            try:
                await self._checkpoint_conn.close()
            except Exception:
                pass
            self._checkpoint_conn = None

    def _build_graph(self, checkpointer):
        graph = StateGraph(AnalysisState)

        graph.add_node("coordinator", self._coordinator_node)
        graph.add_node("structure", self._structure_node)
        graph.add_node("web_search", self._web_search_node)
        graph.add_node("sde_doc", self._sde_node)
        graph.add_node("pm_doc", self._pm_node)
        graph.add_node("join", self._join_node)

        graph.add_edge("coordinator", "structure")
        graph.add_edge("structure", "web_search")

        graph.add_conditional_edges(
            "web_search",
            self._route_personas,
            {
                "sde_doc": "sde_doc",
                "pm_doc": "pm_doc"
            }
        )

        graph.add_edge("sde_doc", "join")
        graph.add_edge("pm_doc", "join")
        graph.add_edge("join", END)

        graph.set_entry_point("coordinator")
        return graph.compile(checkpointer=checkpointer)

    def _route_personas(self, state: AnalysisState):
        routes = []
        if state.get("run_sde"):
            routes.append("sde_doc")
        if state.get("run_pm"):
            routes.append("pm_doc")
        return routes or ["pm_doc"]

    async def _coordinator_node(self, state: AnalysisState) -> Dict[str, Any]:
        return await self.coordinator.run(state, self.db, self.progress)

    async def _structure_node(self, state: AnalysisState) -> Dict[str, Any]:
        out = await self.structure.run(state, self.db, self.progress)
        if state.get("analysis_id"):
            await self.progress.update_progress(
                state["analysis_id"],
                processed_files=20,
                total_files=100,
            )
        return out

    async def _web_search_node(self, state: AnalysisState) -> Dict[str, Any]:
        out = await self.web_search.run(state, self.db, self.progress)
        if state.get("analysis_id"):
            await self.progress.update_progress(
                state["analysis_id"],
                processed_files=40,
                total_files=100,
            )
        return out

    async def _sde_node(self, state: AnalysisState) -> Dict[str, Any]:
        updates = await self.human_input.run(state, self.db, self.progress)
        merged = dict(state)
        merged.update(updates)
        out = await self.sde_agent.run(merged, self.db, self.progress)
        if state.get("analysis_id"):
            await self.progress.update_progress(
                state["analysis_id"],
                processed_files=60,
                total_files=100,
            )
        return out

    async def _pm_node(self, state: AnalysisState) -> Dict[str, Any]:
        updates = await self.human_input.run(state, self.db, self.progress)
        merged = dict(state)
        merged.update(updates)
        out = await self.pm_agent.run(merged, self.db, self.progress)
        if state.get("analysis_id"):
            await self.progress.update_progress(
                state["analysis_id"],
                processed_files=80,
                total_files=100,
            )
        return out

    async def _join_node(self, state: AnalysisState) -> Dict[str, Any]:
        if state.get("analysis_id"):
            await self.progress.update_progress(
                state["analysis_id"],
                processed_files=100,
                total_files=100,
            )
        return {}

    async def run(self, initial_state: AnalysisState) -> AnalysisState:
        checkpointer = await self._get_checkpointer()
        graph = self._build_graph(checkpointer)
        thread_id = f"analysis-{initial_state['analysis_id']}"
        config = {"configurable": {"thread_id": thread_id}}
        payload: Any = initial_state

        while True:
            result = await graph.ainvoke(payload, config=config)
            if "__interrupt__" not in result:
                return result

            interrupts = result.get("__interrupt__") or []
            first = interrupts[0] if interrupts else None
            interrupt_value = getattr(first, "value", first)
            resume_value = None
            if isinstance(interrupt_value, dict) and interrupt_value.get("resume_with") is not None:
                resume_value = interrupt_value["resume_with"]
                await self.progress.log_event(
                    analysis_id=initial_state["analysis_id"],
                    level="info",
                    message="Applying user context update",
                    stage="agent_orchestration"
                )
            else:
                prompt_text = interrupt_value
                if isinstance(interrupt_value, dict):
                    try:
                        prompt_text = json.dumps(interrupt_value, ensure_ascii=True)
                    except TypeError:
                        prompt_text = str(interrupt_value)
                await self.progress.log_event(
                    analysis_id=initial_state["analysis_id"],
                    level="info",
                    message=f"Interrupt received without resume payload: {prompt_text}",
                    stage="agent_orchestration"
                )
                analysis = await self.progress.get_analysis(initial_state["analysis_id"])
                instructions = []
                if analysis and analysis.user_context:
                    instructions = analysis.user_context.get("instructions", []) or []
                latest = instructions[-1] if instructions else {}
                resume_value = {
                    "text": latest.get("text", ""),
                    "scope": latest.get("scope", "global")
                }

            payload = Command(resume=resume_value)
