"""Analysis runner that executes preprocessing and agent orchestration."""
import asyncio
import json
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import AsyncSessionLocal
from src.services.analysis_progress import AnalysisProgressService, PauseTimeoutError
from src.services.analysis_orchestrator import AnalysisOrchestrator
from src.services.code_chunker import CodeChunker
from src.models.analysis import Analysis, AnalysisStage, AnalysisStatus, AnalysisArtifact
from src.models.project import Project, SourceType
from src.services.project_service import ProjectService


async def _wait_if_paused(progress: AnalysisProgressService, analysis_id: UUID):
    """Pause gate that waits while analysis is paused."""
    await progress.wait_if_paused(analysis_id)


async def run_analysis_job(analysis_id: UUID) -> None:
    """Run full analysis pipeline for the given analysis ID."""
    async with AsyncSessionLocal() as db:
        progress = AnalysisProgressService(db)

        analysis = await progress.get_analysis(analysis_id)
        if not analysis:
            return

        skip_preprocessing = analysis.current_stage in {
            AnalysisStage.AGENT_ORCHESTRATION,
            AnalysisStage.DOCUMENTATION_GENERATION
        }

        result = await db.execute(
            select(Project).where(Project.id == analysis.project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            await progress.fail_analysis(analysis_id, "Project not found")
            return

        try:
            if not skip_preprocessing:
                await progress.start_analysis(analysis_id)

                # Preprocessing stage
                code_chunker = CodeChunker(db)
                code_chunker.pause_checker = lambda: progress.wait_if_paused(analysis_id)
                code_chunker.set_analysis_context(progress, analysis_id)

                async def progress_callback(event: dict):
                    event_type = event.get("type")
                    stage = event.get("stage")

                    if event_type == "progress":
                        if stage == "code_chunking":
                            current_stage = AnalysisStage.CODE_CHUNKING
                        elif stage == "embedding_generation":
                            current_stage = AnalysisStage.EMBEDDING_GENERATION
                        else:
                            current_stage = AnalysisStage.REPO_SCAN
                        await progress.update_progress(
                            analysis_id=analysis_id,
                            stage=current_stage,
                            processed_files=event.get("file_index"),
                            total_files=event.get("total_files")
                        )
                        await progress.log_event(
                            analysis_id=analysis_id,
                            level="info",
                            message=f"{stage}: {event.get('current_file')}",
                            stage=stage,
                            current_file=event.get("current_file"),
                            file_index=event.get("file_index"),
                            total_files=event.get("total_files"),
                            progress_percentage=event.get("percent")
                        )
                    elif event_type == "log":
                        await progress.log_event(
                            analysis_id=analysis_id,
                            level=event.get("level", "info"),
                            message=event.get("message", ""),
                            stage=event.get("stage")
                        )
                    elif event_type == "completed":
                        await progress.log_event(
                            analysis_id=analysis_id,
                            level="milestone",
                            message="Preprocessing completed",
                            stage="preprocessing"
                        )

                code_chunker.progress_callback = progress_callback

                await _wait_if_paused(progress, analysis_id)
                extracted_path = f"projects/{str(project.id)}/extracted"
                if project.source_type == SourceType.GITHUB:
                    project_service = ProjectService(db)
                    extracted_path = await project_service.clone_github_repo(
                        str(project.id),
                        project.source_path
                    )

                await code_chunker.preprocess_project(str(project.id), extracted_path)

                # Restart progress from 0 for agent phase so 100% only when entire job is done
                await progress.update_progress(
                    analysis_id=analysis_id,
                    stage=AnalysisStage.AGENT_ORCHESTRATION,
                    processed_files=0,
                    total_files=100,
                )
                await db.execute(
                    Analysis.__table__.update()
                    .where(Analysis.id == analysis_id)
                    .values(status=AnalysisStatus.ANALYZING)
                )
                await db.commit()
            else:
                await progress.log_event(
                    analysis_id=analysis_id,
                    level="info",
                    message="Resuming agent orchestration from checkpoint",
                    stage="agent_orchestration"
                )

            await _wait_if_paused(progress, analysis_id)
            await progress.log_event(
                analysis_id=analysis_id,
                level="milestone",
                message="Starting LangGraph agent orchestration",
                stage="agent_orchestration"
            )
            options = analysis.user_context or {}
            instructions = options.get("instructions", []) or []
            if instructions:
                latest = instructions[-1]
                text = latest.get("text") if isinstance(latest, dict) else str(latest)
                if text:
                    await progress.log_event(
                        analysis_id=analysis_id,
                        level="info",
                        message=f"Initial suggestions: {text[:200]}",
                        stage="agent_orchestration"
                    )

            orchestrator = AnalysisOrchestrator(db, progress)
            try:
                final_state = await orchestrator.run({
                    "analysis_id": analysis_id,
                    "project_id": project.id,
                    "analysis_depth": analysis.analysis_depth,
                    "verbosity_level": analysis.verbosity_level,
                    "target_personas": analysis.target_personas or {},
                    "analysis_options": analysis.user_context or {}
                })
            finally:
                await orchestrator.close()

            await progress.update_progress(
                analysis_id=analysis_id,
                stage=AnalysisStage.DOCUMENTATION_GENERATION
            )

            await progress.log_event(
                analysis_id=analysis_id,
                level="milestone",
                message="Agent orchestration completed",
                stage="documentation_generation"
            )

            # Persist artifacts (basic for M4)
            artifacts = []
            if final_state.get("sde_output"):
                artifacts.append(AnalysisArtifact(
                    analysis_id=analysis_id,
                    artifact_type="sde_report",
                    persona="sde",
                    content=final_state["sde_output"],
                    format="markdown",
                    title="SDE Summary"
                ))
            if final_state.get("sde_structured"):
                artifacts.append(AnalysisArtifact(
                    analysis_id=analysis_id,
                    artifact_type="sde_report_structured",
                    persona="sde",
                    content=json.dumps(final_state["sde_structured"], ensure_ascii=True),
                    format="json",
                    title="SDE Summary (Structured)"
                ))
            if final_state.get("pm_output"):
                artifacts.append(AnalysisArtifact(
                    analysis_id=analysis_id,
                    artifact_type="pm_report",
                    persona="pm",
                    content=final_state["pm_output"],
                    format="markdown",
                    title="PM Summary"
                ))
            if final_state.get("web_findings"):
                artifacts.append(AnalysisArtifact(
                    analysis_id=analysis_id,
                    artifact_type="web_findings",
                    content=final_state["web_findings"],
                    format="markdown",
                    title="Web Research Findings"
                ))

            options = analysis.user_context or {}
            if options.get("enable_diagrams"):
                prefs = options.get("diagram_preferences", [])
                artifacts.append(AnalysisArtifact(
                    analysis_id=analysis_id,
                    artifact_type="diagram_preferences",
                    content=f"Requested diagrams: {', '.join(prefs) if prefs else 'default'}",
                    format="text",
                    title="Diagram Preferences"
                ))

                repo_summary = final_state.get("repo_summary", {})
                diagrams = _build_diagram_artifacts(
                    analysis_id=analysis_id,
                    repo_summary=repo_summary,
                    preferences=prefs
                )
                artifacts.extend(diagrams)

            if artifacts:
                # Use a fresh session for final artifact writes to avoid long-lived session issues
                async with AsyncSessionLocal() as write_session:
                    write_session.add_all(artifacts)
                    await write_session.commit()

            await progress.log_event(
                analysis_id=analysis_id,
                level="milestone",
                message="Analysis completed",
                stage="completed"
            )
            # Final status update with a fresh session to avoid prepared/invalid states
            async with AsyncSessionLocal() as final_session:
                final_progress = AnalysisProgressService(final_session)
                await final_progress.complete_analysis(analysis_id)

        except PauseTimeoutError:
            return
        except Exception as e:
            try:
                await progress.log_event(
                    analysis_id=analysis_id,
                    level="error",
                    message=f"Analysis failed: {str(e)[:200]}",
                    stage="failed"
                )
            except Exception:
                pass
            await progress.fail_analysis(analysis_id, str(e))


def _mermaid_safe(s: str, max_len: int = 40) -> str:
    """Escape and truncate label for Mermaid (no brackets, newlines, or long text)."""
    if not s:
        return ""
    s = str(s).replace("[", "(").replace("]", ")").replace('"', "'").strip()
    return s[:max_len] + ("..." if len(s) > max_len else "")


def _build_diagram_artifacts(analysis_id: UUID, repo_summary: dict, preferences: list) -> list:
    """Build Mermaid diagram artifacts from repo summary (architecture, sequence, flowchart, ER)."""
    prefs = preferences or ["architecture"]
    artifacts = []

    repo_type = repo_summary.get("repository_type", "repo")
    framework = repo_summary.get("primary_framework") or "framework"
    entry_points = repo_summary.get("entry_points", {}) or {}
    entry_list = list(entry_points.values()) or []
    entrypoint_files = repo_summary.get("entrypoint_files") or []
    api_routes = repo_summary.get("api_routes") or []
    model_hints = repo_summary.get("model_hints") or []
    config_files = repo_summary.get("config_files") or []

    # Short names for entrypoints (filename only)
    entry_names = entry_list[:5]
    if not entry_names and entrypoint_files:
        entry_names = [p.split("/")[-1].split("\\")[-1] for p in entrypoint_files[:5]]
    if not entry_names:
        entry_names = ["app entry"]

    if "architecture" in prefs:
        api_label = f"{repo_type} {framework} API"
        lines = [
            "flowchart LR",
            f"    Client[Client] --> API[{_mermaid_safe(api_label)}]",
        ]
        # Entrypoints as subgraph or single node
        ep_label = ", ".join(_mermaid_safe(n, 20) for n in entry_names[:4])
        lines.append(f"    API --> EP[Entrypoints: {_mermaid_safe(ep_label, 50)}]")
        # API routes count and sample
        if api_routes:
            path_samples = sorted(set((r.get("path") or "").split("/")[1] or "api" for r in api_routes[:20]))[:4]
            routes_label = f"{len(api_routes)} routes" + (f" e.g. /{path_samples[0]}" if path_samples else "")
            lines.append(f"    API --> Routes[{_mermaid_safe(routes_label)}]")
        else:
            lines.append("    API --> Routes[API Routes]")
        # Models
        if model_hints:
            models_label = ", ".join(model_hints[:6]) if len(model_hints) <= 8 else f"{len(model_hints)} models e.g. {', '.join(model_hints[:3])}"
            lines.append(f"    API --> Models[{_mermaid_safe(models_label, 45)}]")
        lines.append("    API --> DB[(Database)]")
        if config_files:
            cfg_label = ", ".join(_mermaid_safe(c.split("/")[-1].split("\\")[-1], 15) for c in config_files[:3])
            lines.append(f"    API -.-> Config[{_mermaid_safe(cfg_label, 40)}]")
        diagram = "\n".join(lines)
        artifacts.append(AnalysisArtifact(
            analysis_id=analysis_id,
            artifact_type="diagram_architecture",
            content=diagram,
            format="mermaid",
            title="Architecture Diagram"
        ))

    if "sequence" in prefs:
        lines = ["sequenceDiagram", "    participant Client", "    participant API", "    participant DB"]
        if api_routes:
            for r in api_routes[:5]:
                method = (r.get("method") or "GET").upper()
                path = (r.get("path") or "/").strip()
                path_short = path if len(path) <= 32 else path[:29] + "..."
                lines.append(f"    Client->>API: {method} {path_short}")
                lines.append("    API->>DB: Query / Validate")
                lines.append("    DB-->>API: Result")
                lines.append("    API-->>Client: Response")
        else:
            # Generic but named flows using model hints
            auth_models = [m for m in model_hints if "Login" in m or "Token" in m or "User" in m][:2]
            auth_msg = f"Login / {auth_models[0]}" if auth_models else "Login"
            lines.extend([
                f"    Client->>API: {auth_msg}",
                "    API->>DB: Validate credentials",
                "    DB-->>API: User / Token",
                "    API-->>Client: Token / UserResponse",
                "    Client->>API: List / Create (e.g. Projects)",
                "    API->>DB: Query",
                "    DB-->>API: Result",
                "    API-->>Client: ListResponse",
            ])
        diagram = "\n".join(lines)
        artifacts.append(AnalysisArtifact(
            analysis_id=analysis_id,
            artifact_type="diagram_sequence",
            content=diagram,
            format="mermaid",
            title="Sequence Diagram"
        ))

    if "flowchart" in prefs:
        # Request flow derived from route path segments when possible, else analysis pipeline
        if api_routes:
            path_groups = sorted(set((r.get("path") or "/").strip().split("/")[1] or "api" for r in api_routes[:30]))
            steps = path_groups[:6]
            lines_flow = ["flowchart TD", "    Start[Client] --> API[API]"]
            prev = "API"
            for i, seg in enumerate(steps):
                node_id = f"S{i}"
                label = seg if seg else "api"
                lines_flow.append(f"    {prev} --> {node_id}[{_mermaid_safe(label, 25)}]")
                prev = node_id
            lines_flow.append(f"    {prev} --> Response[Response]")
            diagram = "\n".join(lines_flow)
        else:
            diagram = (
                "flowchart TD\n"
                "    Start[Start] --> Scan[Repo scan]\n"
                "    Scan --> Chunk[Code chunking]\n"
                "    Chunk --> Embed[Embeddings]\n"
                "    Embed --> Agents[Agent orchestration]\n"
                "    Agents --> End[Done]\n"
            )
        artifacts.append(AnalysisArtifact(
            analysis_id=analysis_id,
            artifact_type="diagram_flowchart",
            content=diagram,
            format="mermaid",
            title="Request Flow" if api_routes else "Analysis Flowchart"
        ))

    if "entity_relationship" in prefs:
        # Use model_hints for entity names when present
        if model_hints:
            entities = [m.upper().replace(" ", "_")[:20] for m in model_hints[:8]]
            lines_er = ["erDiagram"]
            if "User" in " ".join(model_hints) or "USER" in " ".join(entities):
                lines_er.append("    USER ||--o{ PROJECT : owns")
            if "Project" in " ".join(model_hints) or "PROJECT" in " ".join(entities):
                lines_er.append("    PROJECT ||--o{ ANALYSIS : has")
            lines_er.append("    PROJECT ||--o{ CODE_CHUNK : contains")
            lines_er.append("    ANALYSIS ||--o{ ANALYSIS_LOG : logs")
            if "AnalysisArtifact" in " ".join(model_hints):
                lines_er.append("    ANALYSIS ||--o{ ANALYSIS_ARTIFACT : produces")
            diagram = "\n".join(lines_er)
        else:
            diagram = (
                "erDiagram\n"
                "    USER ||--o{ PROJECT : owns\n"
                "    PROJECT ||--o{ ANALYSIS : has\n"
                "    PROJECT ||--o{ CODE_CHUNK : contains\n"
                "    ANALYSIS ||--o{ ANALYSIS_LOG : logs\n"
            )
        artifacts.append(AnalysisArtifact(
            analysis_id=analysis_id,
            artifact_type="diagram_er",
            content=diagram,
            format="mermaid",
            title="Entity Relationship Diagram"
        ))

    return artifacts
