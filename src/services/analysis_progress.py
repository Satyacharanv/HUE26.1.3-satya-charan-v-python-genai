"""Analysis progress tracking service"""
import logging
import asyncio
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from src.models.analysis import Analysis, AnalysisLog, AnalysisStatus, AnalysisStage, AnalysisInteraction
from src.database import AsyncSessionLocal
from src.core.config import settings

logger = logging.getLogger(__name__)


class PauseTimeoutError(Exception):
    """Raised when a paused analysis exceeds the timeout window."""


class AnalysisProgressService:
    """Service for tracking and updating analysis progress"""

    PAUSE_ALLOWED_STAGES = {
        AnalysisStage.REPO_SCAN,
        AnalysisStage.CODE_CHUNKING,
        AnalysisStage.EMBEDDING_GENERATION,
        AnalysisStage.AGENT_ORCHESTRATION
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_analysis(
        self,
        project_id: UUID,
        analysis_depth: str = "standard",
        target_personas: dict = None,
        verbosity_level: str = "normal",
        user_context: dict = None
    ) -> Analysis:
        """Create a new analysis job"""
        analysis = Analysis(
            project_id=project_id,
            analysis_depth=analysis_depth,
            target_personas=target_personas or {"sde": True, "pm": True},
            verbosity_level=verbosity_level,
            user_context=user_context or {},
            status=AnalysisStatus.PENDING
        )
        
        self.db.add(analysis)
        await self.db.flush()
        
        logger.debug(f"Created analysis {analysis.id} for project {project_id}")
        return analysis
    
    async def start_analysis(self, analysis_id: UUID) -> None:
        """Mark analysis as started"""
        await self.db.execute(
            update(Analysis).where(Analysis.id == analysis_id).values(
                status=AnalysisStatus.PREPROCESSING,
                current_stage=AnalysisStage.REPO_SCAN,
                started_at=datetime.utcnow()
            )
        )
        await self.db.commit()
        logger.debug(f"Started analysis {analysis_id}")
    
    async def update_progress(
        self,
        analysis_id: UUID,
        stage: AnalysisStage = None,
        processed_files: int = None,
        total_files: int = None,
        processed_chunks: int = None,
        total_chunks: int = None,
        tokens_used: int = None,
        estimated_cost: float = None
    ) -> None:
        """Update analysis progress"""
        values = {}
        
        if stage:
            values['current_stage'] = stage
        if processed_files is not None:
            values['processed_files'] = processed_files
        if total_files is not None:
            values['total_files'] = total_files
        if processed_chunks is not None:
            values['processed_chunks'] = processed_chunks
        if total_chunks is not None:
            values['total_chunks'] = total_chunks
        if tokens_used is not None:
            values['total_tokens_used'] = tokens_used
        if estimated_cost is not None:
            values['estimated_cost'] = estimated_cost
        
        if values:
            # Use a dedicated session to avoid concurrent operations on the shared session
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(Analysis).where(Analysis.id == analysis_id).values(**values)
                )
                await session.commit()
            try:
                from src.api.v1.websocket_progress import broadcast_progress
                await broadcast_progress(
                    analysis_id=analysis_id,
                    stage=stage.value if stage else None,
                    message="progress_update",
                    current_file=None,
                    file_index=processed_files,
                    total_files=total_files,
                    processed_chunks=processed_chunks,
                    total_chunks=total_chunks,
                    tokens_used=tokens_used,
                    estimated_cost=estimated_cost,
                    level="info"
                )
            except Exception:
                pass
    
    async def log_event(
        self,
        analysis_id: UUID,
        level: str,  # info, warning, error, milestone
        message: str,
        stage: str = None,
        current_file: str = None,
        file_index: int = None,
        total_files: int = None,
        progress_percentage: float = None
    ) -> AnalysisLog:
        """Log analysis event"""
        log = AnalysisLog(
            analysis_id=analysis_id,
            level=level,
            message=message,
            stage=stage,
            current_file=current_file,
            file_index=file_index,
            total_files=total_files,
            progress_percentage=progress_percentage,
            timestamp=datetime.utcnow()
        )

        # Use a dedicated session to avoid concurrent commits
        async with AsyncSessionLocal() as session:
            session.add(log)
            await session.commit()

        try:
            from src.api.v1.websocket_progress import broadcast_log
            await broadcast_log(
                analysis_id=analysis_id,
                level=level,
                message=message,
                stage=stage,
                current_file=current_file,
                file_index=file_index,
                total_files=total_files,
                progress_percentage=progress_percentage
            )
        except Exception:
            pass
        
        return log

    def is_pause_allowed(self, analysis: Analysis) -> bool:
        """Check if pause is allowed for the analysis stage."""
        if analysis.current_stage in self.PAUSE_ALLOWED_STAGES:
            return True
        # Allow pause if we're analyzing but stage wasn't set yet.
        if analysis.status == AnalysisStatus.ANALYZING and analysis.current_stage is None:
            return True
        return False

    async def wait_if_paused(self, analysis_id: UUID, poll_seconds: float = 0.5) -> None:
        """Block until analysis resumes or times out."""
        logged_waiting = False
        logged_timeout = False
        while True:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Analysis).where(Analysis.id == analysis_id)
                )
                analysis = result.scalar_one_or_none()
            if not analysis or not analysis.paused:
                if logged_waiting:
                    try:
                        await self.log_event(
                            analysis_id=analysis_id,
                            level="info",
                            message="Pause gate released; resuming work",
                            stage=analysis.current_stage.value if analysis and analysis.current_stage else None
                        )
                    except Exception:
                        pass
                return
            if not self.is_pause_allowed(analysis):
                return
            if analysis.paused_at:
                timeout_seconds = max(0, settings.PAUSE_TIMEOUT_MINUTES) * 60
                if timeout_seconds > 0:
                    if datetime.utcnow() - analysis.paused_at > timedelta(seconds=timeout_seconds):
                        if not logged_timeout:
                            logged_timeout = True
                            try:
                                await self.log_event(
                                    analysis_id=analysis_id,
                                    level="warning",
                                    message="Pause timeout exceeded; cancelling analysis",
                                    stage=analysis.current_stage.value if analysis.current_stage else None
                                )
                            except Exception:
                                pass
                        await self.cancel_analysis(analysis_id, "Pause timeout exceeded")
                        raise PauseTimeoutError("Pause timeout exceeded")
            if not logged_waiting:
                logged_waiting = True
                try:
                    await self.log_event(
                        analysis_id=analysis_id,
                        level="info",
                        message="Pause gate waiting for resume",
                        stage=analysis.current_stage.value if analysis.current_stage else None
                    )
                except Exception:
                    pass
            await asyncio.sleep(poll_seconds)

    async def wait_for_context_response(
        self,
        analysis_id: UUID,
        since: datetime,
        poll_seconds: float = 0.5
    ) -> AnalysisInteraction:
        """Wait for a new context interaction after a timestamp."""
        while True:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(AnalysisInteraction)
                    .where(
                        AnalysisInteraction.analysis_id == analysis_id,
                        AnalysisInteraction.kind == "context",
                        AnalysisInteraction.timestamp > since
                    )
                    .order_by(AnalysisInteraction.timestamp.asc())
                    .limit(1)
                )
                interaction = result.scalar_one_or_none()
            if interaction:
                return interaction
            await asyncio.sleep(poll_seconds)
    
    async def pause_analysis(self, analysis_id: UUID) -> None:
        """Pause analysis"""
        analysis = await self.get_analysis(analysis_id)
        await self.db.execute(
            update(Analysis).where(Analysis.id == analysis_id).values(
                status=AnalysisStatus.PAUSED,
                paused=True,
                paused_at=datetime.utcnow()
            )
        )
        await self.db.commit()
        logger.debug(f"Paused analysis {analysis_id}")
        try:
            await self.log_event(
                analysis_id=analysis_id,
                level="info",
                message="Analysis paused by user",
                stage=analysis.current_stage.value if analysis and analysis.current_stage else None
            )
        except Exception:
            pass

    async def cancel_analysis(self, analysis_id: UUID, reason: str = "Cancelled") -> None:
        """Cancel analysis and stop processing."""
        await self.db.execute(
            update(Analysis).where(Analysis.id == analysis_id).values(
                status=AnalysisStatus.CANCELLED,
                paused=False,
                error_message=reason,
                completed_at=datetime.utcnow()
            )
        )
        await self.db.commit()
        logger.debug(f"Cancelled analysis {analysis_id}: {reason}")
        try:
            await self.log_event(
                analysis_id=analysis_id,
                level="warning",
                message=f"Analysis cancelled: {reason}",
                stage=None
            )
        except Exception:
            pass
    
    async def resume_analysis(self, analysis_id: UUID) -> None:
        """Resume analysis"""
        analysis = await self.get_analysis(analysis_id)
        next_status = AnalysisStatus.ANALYZING
        if analysis and self.is_pause_allowed(analysis):
            next_status = AnalysisStatus.PREPROCESSING
        await self.db.execute(
            update(Analysis).where(Analysis.id == analysis_id).values(
                status=next_status,
                paused=False
            )
        )
        await self.db.commit()
        logger.debug(f"Resumed analysis {analysis_id}")
        try:
            await self.log_event(
                analysis_id=analysis_id,
                level="info",
                message="Analysis resumed by user",
                stage=analysis.current_stage.value if analysis and analysis.current_stage else None
            )
        except Exception:
            pass

    async def reset_analysis_for_restart(self, analysis_id: UUID, restart_stage: str) -> None:
        """Reset analysis state to allow restart after timeout."""
        values = {
            "paused": False,
            "paused_at": None,
            "completed_at": None,
            "error_message": None,
        }
        if restart_stage == "preprocessing":
            values.update({
                "status": AnalysisStatus.PREPROCESSING,
                "current_stage": AnalysisStage.REPO_SCAN,
                "processed_files": 0,
                "total_files": 0,
                "processed_chunks": 0,
                "total_chunks": 0,
                "total_tokens_used": 0,
                "estimated_cost": 0.0,
                "started_at": datetime.utcnow(),
            })
        else:
            values.update({
                "status": AnalysisStatus.ANALYZING,
                "current_stage": AnalysisStage.AGENT_ORCHESTRATION,
            })
        await self.db.execute(
            update(Analysis).where(Analysis.id == analysis_id).values(**values)
        )
        await self.db.commit()
        try:
            await self.log_event(
                analysis_id=analysis_id,
                level="info",
                message=f"Analysis reset for restart ({restart_stage})",
                stage=values.get("current_stage").value if values.get("current_stage") else None
            )
        except Exception:
            pass
    
    async def complete_analysis(self, analysis_id: UUID) -> None:
        """Mark analysis as completed"""
        analysis = await self.get_analysis(analysis_id)
        if analysis:
            existing = analysis.user_context or {}
            if existing.get("pending_context"):
                existing["pending_context"] = False
                analysis.user_context = existing
                await self.db.commit()
        await self.db.execute(
            update(Analysis).where(Analysis.id == analysis_id).values(
                status=AnalysisStatus.COMPLETED,
                current_stage=AnalysisStage.COMPLETED,
                completed_at=datetime.utcnow(),
                processed_files=100,
                total_files=100,
            )
        )
        await self.db.commit()
        logger.info(f"Analysis completed: {analysis_id}")
    
    async def fail_analysis(self, analysis_id: UUID, error_message: str) -> None:
        """Mark analysis as failed"""
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Analysis).where(Analysis.id == analysis_id).values(
                    status=AnalysisStatus.FAILED,
                    error_message=error_message,
                    completed_at=datetime.utcnow()
                )
            )
            await session.commit()
        logger.error(f"Analysis {analysis_id} failed: {error_message}")
    
    async def get_analysis(self, analysis_id: UUID) -> Analysis:
        """Get analysis by ID"""
        result = await self.db.execute(
            select(Analysis)
            .where(Analysis.id == analysis_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()
    
    async def add_user_context(self, analysis_id: UUID, context: dict) -> None:
        """Add user-provided context to analysis"""
        analysis = await self.get_analysis(analysis_id)
        if analysis:
            if analysis.status in {AnalysisStatus.COMPLETED, AnalysisStatus.FAILED, AnalysisStatus.CANCELLED}:
                try:
                    await self.log_event(
                        analysis_id=analysis_id,
                        level="warning",
                        message="Context received after analysis completion; no agents to interrupt",
                        stage=analysis.current_stage.value if analysis.current_stage else None
                    )
                except Exception:
                    pass
                return
            existing = analysis.user_context or {}
            instructions = existing.get("instructions", [])
            instructions.append(context)
            existing["instructions"] = instructions
            if analysis.current_stage == AnalysisStage.AGENT_ORCHESTRATION:
                existing["pending_context"] = True
            analysis.user_context = existing
            await self.db.commit()
            text = context.get("text") or context.get("instruction") or ""
            scope = context.get("scope") or "global"
            stage = analysis.current_stage.value if analysis.current_stage else None
            try:
                await self.log_event(
                    analysis_id=analysis_id,
                    level="info",
                    message=f"Context added (scope={scope}): {text[:200]}",
                    stage=stage
                )
                if analysis.current_stage == AnalysisStage.AGENT_ORCHESTRATION:
                    await self.log_event(
                        analysis_id=analysis_id,
                        level="info",
                        message="Context queued for agent interruption",
                        stage=stage
                    )
            except Exception:
                pass

    async def add_interaction(
        self,
        analysis_id: UUID,
        kind: str,
        content: str,
        scope: str | None = None,
        response: str | None = None
    ) -> AnalysisInteraction:
        """Persist a user interaction (question/context)."""
        interaction = AnalysisInteraction(
            analysis_id=analysis_id,
            kind=kind,
            scope=scope,
            content=content,
            response=response,
            timestamp=datetime.utcnow()
        )
        async with AsyncSessionLocal() as session:
            session.add(interaction)
            await session.commit()
        return interaction
    
    async def get_analysis_logs(self, analysis_id: UUID, limit: int = 100) -> list:
        """Get recent analysis logs"""
        result = await self.db.execute(
            select(AnalysisLog)
            .where(AnalysisLog.analysis_id == analysis_id)
            .order_by(AnalysisLog.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()
