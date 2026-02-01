"""Analysis management endpoints"""
import asyncio
import json
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from src.core.logging_config import get_logger

from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.models.project import Project
from src.models.analysis import Analysis, AnalysisArtifact, AnalysisLog, AnalysisStatus, AnalysisStage
from src.models.analysis_template import AnalysisTemplate
from src.models.repository_metadata import RepositoryMetadata
from src.services.analysis_progress import AnalysisProgressService
from src.services.analysis_runner import run_analysis_job
from src.services.semantic_search import SemanticSearchService
from src.services.export_service import build_markdown, build_pdf
from src.database import AsyncSessionLocal

logger = get_logger(__name__)
router = APIRouter(prefix="/analysis", tags=["analysis"])


class AnalysisConfigRequest(BaseModel):
    """Request to start analysis"""
    project_id: str
    analysis_depth: str = "standard"  # quick, standard, deep
    target_personas: dict = None
    verbosity_level: str = "normal"  # low, normal, high
    enable_web_search: bool = True
    enable_diagrams: bool = True
    diagram_preferences: list[str] = []
    initial_context: str | None = None


class AnalysisResponse(BaseModel):
    """Analysis response"""
    id: str
    project_id: str
    status: str
    current_stage: str
    progress: dict
    tokens_used: int
    estimated_cost: float
    configuration: dict | None = None
    started_at: str | None = None
    completed_at: str | None = None


class AnalysisControlRequest(BaseModel):
    """Request to control analysis"""
    action: str  # pause, resume
    context: dict = None


class AnalysisAskRequest(BaseModel):
    """Request to ask a question during analysis"""
    question: str


class AnalysisTemplateRequest(BaseModel):
    """Request to create analysis template"""
    name: str
    description: str | None = None
    config: dict


@router.post("/create")
async def create_analysis(
    request: AnalysisConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Create and start a new analysis job
    
    This endpoint:
    1. Verifies project ownership
    2. Creates analysis record
    3. Queues the analysis for background processing
    """
    
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == UUID(request.project_id),
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied"
        )
    
    # Create analysis
    progress_service = AnalysisProgressService(db)
    analysis_options = {
        "enable_web_search": request.enable_web_search,
        "enable_diagrams": request.enable_diagrams,
        "diagram_preferences": request.diagram_preferences
    }
    if request.initial_context and request.initial_context.strip():
        analysis_options["instructions"] = [{
            "text": request.initial_context.strip(),
            "scope": "global",
            "timestamp": datetime.utcnow().isoformat()
        }]

    analysis = await progress_service.create_analysis(
        project_id=UUID(request.project_id),
        analysis_depth=request.analysis_depth,
        target_personas=request.target_personas or {"sde": True, "pm": True},
        verbosity_level=request.verbosity_level,
        user_context=analysis_options
    )
    
    await db.commit()
    if request.initial_context and request.initial_context.strip():
        try:
            await progress_service.log_event(
                analysis_id=analysis.id,
                level="info",
                message=f"Initial suggestions recorded: {request.initial_context.strip()[:200]}",
                stage="setup"
            )
            await progress_service.add_interaction(
                analysis_id=analysis.id,
                kind="context",
                content=request.initial_context.strip(),
                scope="global"
            )
        except Exception:
            pass
    
    # Run analysis in background (LangGraph orchestration)
    asyncio.create_task(run_analysis_job(analysis.id))
    
    return {
        "analysis_id": str(analysis.id),
        "status": "queued",
        "message": "Analysis job created and started",
        "configuration": {
            "depth": request.analysis_depth,
            "personas": request.target_personas,
            "verbosity": request.verbosity_level,
            "enable_web_search": request.enable_web_search,
            "enable_diagrams": request.enable_diagrams,
            "diagram_preferences": request.diagram_preferences
        }
    }


@router.get("/templates")
async def list_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    result = await db.execute(
        select(AnalysisTemplate).where(AnalysisTemplate.owner_id == current_user.id)
    )
    templates = result.scalars().all()
    return {
        "templates": [
            {
                "id": str(t.id),
                "name": t.name,
                "description": t.description,
                "config": t.config
            }
            for t in templates
        ]
    }


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    request: AnalysisTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    template = AnalysisTemplate(
        owner_id=current_user.id,
        name=request.name.strip(),
        description=request.description,
        config=request.config
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return {
        "id": str(template.id),
        "name": template.name,
        "description": template.description,
        "config": template.config
    }


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        template_uuid = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    result = await db.execute(
        select(AnalysisTemplate).where(
            AnalysisTemplate.id == template_uuid,
            AnalysisTemplate.owner_id == current_user.id
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    await db.delete(template)
    await db.commit()
    return {"status": "deleted"}


@router.get("/latest")
async def get_latest_analysis(
    project_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Get the latest analysis for the current user (optionally for a specific project).
    """
    try:
        from sqlalchemy import desc

        q = (
            select(Analysis)
            .join(Project, Analysis.project_id == Project.id)
            .where(Project.owner_id == current_user.id)
        )
        if project_id:
            try:
                q = q.where(Project.id == UUID(project_id))
            except ValueError:
                pass
        result = await db.execute(
            q.order_by(desc(Analysis.created_at)).limit(1)
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            return {
                "analysis": None,
                "message": "No analysis found"
            }
        
        # Calculate progress percentage from processed/total
        progress_percent = 0
        if analysis.total_files > 0:
            progress_percent = int((analysis.processed_files / analysis.total_files) * 100)
        
        return {
            "analysis": {
                "id": str(analysis.id),
                "project_id": str(analysis.project_id),
                "status": analysis.status.value,
                "current_stage": analysis.current_stage.value if analysis.current_stage else None,
                "progress_percent": progress_percent,
                "tokens_used": analysis.total_tokens_used,
                "estimated_cost": float(analysis.estimated_cost),
                "created_at": analysis.created_at.isoformat()
            }
        }
    
    except Exception as e:
        logger.error(f"Error fetching latest analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching latest analysis: {str(e)}"
        )


@router.get("/{analysis_id}")
async def get_analysis(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> AnalysisResponse:
    """Get analysis status and progress"""
    
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid analysis ID format"
        )
    
    # Get analysis and verify ownership
    result = await db.execute(
        select(Analysis).where(Analysis.id == analysis_uuid)
    )
    analysis = result.scalar_one_or_none()
    
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found"
        )
    
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == analysis.project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return AnalysisResponse(
        id=str(analysis.id),
        project_id=str(analysis.project_id),
        status=analysis.status.value,
        current_stage=analysis.current_stage.value if analysis.current_stage else None,
        progress={
            "files": f"{analysis.processed_files}/{analysis.total_files}",
            "chunks": f"{analysis.processed_chunks}/{analysis.total_chunks}",
            "percentage": (analysis.processed_files / analysis.total_files * 100) if analysis.total_files > 0 else 0
        },
        tokens_used=analysis.total_tokens_used,
        estimated_cost=analysis.estimated_cost,
        configuration={
            "analysis_depth": analysis.analysis_depth,
            "verbosity_level": analysis.verbosity_level,
            "target_personas": analysis.target_personas,
            "analysis_options": analysis.user_context or {}
        },
        started_at=analysis.started_at.isoformat() if analysis.started_at else None,
        completed_at=analysis.completed_at.isoformat() if analysis.completed_at else None
    )


@router.post("/{analysis_id}/control")
async def control_analysis(
    analysis_id: str,
    request: AnalysisControlRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Control analysis: pause, resume, add context
    """
    
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid analysis ID format"
        )
    
    # Verify ownership
    result = await db.execute(
        select(Analysis).where(Analysis.id == analysis_uuid)
    )
    analysis = result.scalar_one_or_none()
    
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found"
        )
    
    result = await db.execute(
        select(Project).where(
            Project.id == analysis.project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    progress_service = AnalysisProgressService(db)
    
    if request.action == "pause":
        if not progress_service.is_pause_allowed(analysis):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pause is only allowed during preprocessing and embedding stages"
            )
        await progress_service.pause_analysis(analysis_uuid)
        return {"status": "paused", "message": "Analysis paused"}
    
    elif request.action == "resume":
        if analysis.status == AnalysisStatus.CANCELLED:
            reason = (analysis.error_message or "").lower()
            if "pause timeout" in reason:
                restart_stage = (
                    "preprocessing"
                    if analysis.current_stage in progress_service.PAUSE_ALLOWED_STAGES
                    else "agent"
                )
                await progress_service.reset_analysis_for_restart(analysis_uuid, restart_stage)
                asyncio.create_task(run_analysis_job(analysis_uuid))
                return {
                    "status": "restarted",
                    "message": f"Analysis restarted after pause timeout ({restart_stage})"
                }
        await progress_service.resume_analysis(analysis_uuid)
        return {"status": "resumed", "message": "Analysis resumed"}
    
    elif request.action == "add_context":
        if request.context:
            text = request.context.get("text") or request.context.get("instruction")
            scope = request.context.get("scope") or "global"
            if not text:
                raise HTTPException(status_code=400, detail="Context text is required")
            context_entry = {
                "text": text,
                "scope": scope,
                "timestamp": datetime.utcnow().isoformat()
            }
            await progress_service.add_user_context(analysis_uuid, context_entry)
            await progress_service.add_interaction(
                analysis_id=analysis_uuid,
                kind="context",
                content=text,
                scope=scope
            )
        return {"status": "context_added", "message": "User context added"}
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown action: {request.action}"
        )


@router.post("/{analysis_id}/ask")
async def ask_analysis_question(
    analysis_id: str,
    request: AnalysisAskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Ask a question about the analyzed codebase (with citations)."""
    logger.warning(f"Ask analysis: user={current_user.id} analysis_id={analysis_id} question_len={len(request.question)}")
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid analysis ID format")

    # Verify ownership
    result = await db.execute(
        select(Analysis).where(Analysis.id == analysis_uuid)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    result = await db.execute(
        select(Project).where(
            Project.id == analysis.project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=403, detail="Access denied")

    progress_service = AnalysisProgressService(db)
    logs = await progress_service.get_analysis_logs(analysis_uuid, limit=20)
    log_items = [
        {
            "timestamp": log.timestamp.isoformat(),
            "level": log.level,
            "message": log.message,
            "stage": log.stage,
            "file": log.current_file,
            "progress": log.progress_percentage
        }
        for log in logs
    ]

    repo_result = await db.execute(
        select(RepositoryMetadata).where(RepositoryMetadata.project_id == analysis.project_id)
    )
    repo = repo_result.scalar_one_or_none()
    repo_summary = {
        "repository_type": repo.repository_type if repo else None,
        "primary_framework": repo.primary_framework if repo else None,
        "total_files": repo.total_files if repo else 0,
        "code_files": repo.code_files if repo else 0,
        "entry_points": repo.entry_points if repo else {},
    }

    search_service = SemanticSearchService(db)
    answer = await search_service.answer_question(
        project_id=str(project.id),
        question=request.question,
        use_llm=True,
        progress=progress_service,
        analysis_id=analysis_uuid,
    )

    await progress_service.add_interaction(
        analysis_id=analysis_uuid,
        kind="question",
        content=request.question,
        response=answer.get("answer", "")
    )

    logger.info(f"Ask analysis success: analysis_id={analysis_id} response_len={len(answer.get('answer', ''))}")
    return {
        "analysis_id": analysis_id,
        "question": request.question,
        **answer,
    }


@router.get("/{analysis_id}/logs")
async def get_analysis_logs(
    analysis_id: str,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Get analysis activity logs"""
    
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid analysis ID format"
        )
    
    # Verify ownership
    result = await db.execute(
        select(Analysis).where(Analysis.id == analysis_uuid)
    )
    analysis = result.scalar_one_or_none()
    
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found"
        )
    
    result = await db.execute(
        select(Project).where(
            Project.id == analysis.project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    progress_service = AnalysisProgressService(db)
    logs = await progress_service.get_analysis_logs(analysis_uuid, limit=limit)
    
    return {
        "analysis_id": str(analysis_uuid),
        "log_count": len(logs),
        "logs": [
            {
                "timestamp": log.timestamp.isoformat(),
                "level": log.level,
                "message": log.message,
                "stage": log.stage,
                "file": log.current_file,
                "progress": log.progress_percentage
            }
            for log in logs
        ]
    }


@router.get("/{analysis_id}/events")
async def stream_analysis_events(
    analysis_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """Stream analysis progress and logs via SSE."""
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid analysis ID format")

    # Verify ownership
    result = await db.execute(
        select(Analysis).where(Analysis.id == analysis_uuid)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    result = await db.execute(
        select(Project).where(
            Project.id == analysis.project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=403, detail="Access denied")

    async def event_stream():
        last_log_ts = None
        last_progress = None
        while True:
            if await request.is_disconnected():
                break

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Analysis).where(Analysis.id == analysis_uuid)
                )
                current = result.scalar_one_or_none()

            if not current:
                yield "event: end\ndata: {}\n\n"
                break

            progress_payload = {
                "status": current.status.value,
                "current_stage": current.current_stage.value if current.current_stage else None,
                "processed_files": current.processed_files,
                "total_files": current.total_files,
                "processed_chunks": current.processed_chunks,
                "total_chunks": current.total_chunks,
                "tokens_used": current.total_tokens_used,
                "estimated_cost": float(current.estimated_cost),
            }

            if progress_payload != last_progress:
                yield f"event: progress\ndata: {json.dumps(progress_payload)}\n\n"
                last_progress = progress_payload

            async with AsyncSessionLocal() as session:
                if last_log_ts:
                    result = await session.execute(
                        select(AnalysisLog)
                        .where(
                            AnalysisLog.analysis_id == analysis_uuid,
                            AnalysisLog.timestamp > last_log_ts
                        )
                        .order_by(AnalysisLog.timestamp.asc())
                    )
                    logs = result.scalars().all()
                else:
                    result = await session.execute(
                        select(AnalysisLog)
                        .where(AnalysisLog.analysis_id == analysis_uuid)
                        .order_by(AnalysisLog.timestamp.desc())
                        .limit(20)
                    )
                    logs = list(reversed(result.scalars().all()))

            for log in logs:
                payload = {
                    "timestamp": log.timestamp.isoformat(),
                    "level": log.level,
                    "message": log.message,
                    "stage": log.stage,
                    "file": log.current_file,
                    "progress": log.progress_percentage
                }
                yield f"event: log\ndata: {json.dumps(payload)}\n\n"
                last_log_ts = log.timestamp

            if current.status.value in {"completed", "failed", "cancelled"}:
                yield "event: end\ndata: {}\n\n"
                break

            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/{analysis_id}/artifacts")
async def get_analysis_artifacts(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid analysis ID format"
        )

    result = await db.execute(
        select(Analysis).where(Analysis.id == analysis_uuid)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    result = await db.execute(
        select(Project).where(
            Project.id == analysis.project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(AnalysisArtifact).where(AnalysisArtifact.analysis_id == analysis_uuid)
    )
    artifacts = result.scalars().all()

    return {
        "analysis_id": str(analysis_uuid),
        "artifacts": [
            {
                "id": str(a.id),
                "type": a.artifact_type,
                "persona": a.persona,
                "title": a.title,
                "description": a.description,
                "format": a.format,
                "content": a.content
            }
            for a in artifacts
        ]
    }


def _artifact_dicts(artifacts) -> list:
    """Convert artifact ORM list to list of dicts for export."""
    return [
        {
            "type": a.artifact_type,
            "persona": a.persona,
            "title": a.title,
            "format": a.format,
            "content": a.content or "",
        }
        for a in artifacts
    ]


@router.get("/{analysis_id}/export/markdown")
async def export_analysis_markdown(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Export analysis documentation as a single Markdown file."""
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid analysis ID format")
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_uuid))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    result = await db.execute(
        select(Project).where(
            Project.id == analysis.project_id,
            Project.owner_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=403, detail="Access denied")
    result = await db.execute(
        select(AnalysisArtifact).where(AnalysisArtifact.analysis_id == analysis_uuid)
    )
    artifacts = result.scalars().all()
    artifact_list = _artifact_dicts(artifacts)
    out = build_markdown(artifact_list, analysis_id)
    return {"content": out["content"], "filename": out["filename"]}


@router.get("/{analysis_id}/export/pdf", response_class=Response)
async def export_analysis_pdf(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export analysis documentation as PDF (Markdown + Mermaid as image and code block)."""
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid analysis ID format")
    result = await db.execute(select(Analysis).where(Analysis.id == analysis_uuid))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    result = await db.execute(
        select(Project).where(
            Project.id == analysis.project_id,
            Project.owner_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=403, detail="Access denied")
    result = await db.execute(
        select(AnalysisArtifact).where(AnalysisArtifact.analysis_id == analysis_uuid)
    )
    artifacts = result.scalars().all()
    artifact_list = _artifact_dicts(artifacts)
    try:
        pdf_bytes = build_pdf(artifact_list, analysis_id)
    except Exception as e:
        logger.exception("PDF export failed")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="documentation.pdf"'},
    )