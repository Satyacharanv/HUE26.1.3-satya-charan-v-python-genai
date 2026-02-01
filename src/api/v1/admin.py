"""Admin endpoints for system management."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, update
from typing import Dict, Any
from uuid import UUID

from src.database import get_db
from src.api.deps import get_current_admin_user
from src.core.security import get_password_hash
from src.core.logging_config import get_logger
from src.models.user import User, UserRole
from src.models.project import Project, ProjectStatus
from src.models.analysis import Analysis, AnalysisStatus, AnalysisLog
from src.schemas.admin import AdminUserCreate, AdminUserUpdate, AdminProjectUpdate

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _parse_role(value: str) -> UserRole:
    try:
        return UserRole(value)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid role. Use 'user' or 'admin'.")


@router.get("/health")
async def admin_health(
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """System health summary for admins."""
    users_count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    projects_count = (await db.execute(select(func.count()).select_from(Project))).scalar_one()
    analyses_count = (await db.execute(select(func.count()).select_from(Analysis))).scalar_one()

    status_counts = {}
    for status_value in AnalysisStatus:
        count = (
            await db.execute(
                select(func.count()).select_from(Analysis).where(Analysis.status == status_value)
            )
        ).scalar_one()
        status_counts[status_value.value] = count

    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    success_rate = (completed / (completed + failed)) if (completed + failed) > 0 else 0.0

    recent_errors = (
        await db.execute(
            select(AnalysisLog)
            .where(AnalysisLog.level == "error")
            .order_by(AnalysisLog.timestamp.desc())
            .limit(20)
        )
    ).scalars().all()

    return {
        "users": users_count,
        "projects": projects_count,
        "analyses": analyses_count,
        "analysis_status": status_counts,
        "success_rate": round(success_rate, 4),
        "recent_errors": [
            {
                "analysis_id": str(log.analysis_id),
                "timestamp": log.timestamp.isoformat(),
                "message": log.message,
                "stage": log.stage,
            }
            for log in recent_errors
        ],
    }


@router.get("/analyses/running")
async def admin_running_analyses(
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """List currently running analyses."""
    running_statuses = {
        AnalysisStatus.PENDING,
        AnalysisStatus.PREPROCESSING,
        AnalysisStatus.ANALYZING,
        AnalysisStatus.PAUSED,
    }
    rows = (
        await db.execute(
            select(Analysis)
            .where(Analysis.status.in_(running_statuses))
            .order_by(Analysis.started_at.desc())
            .limit(100)
        )
    ).scalars().all()

    return {
        "count": len(rows),
        "analyses": [
            {
                "id": str(a.id),
                "project_id": str(a.project_id),
                "status": a.status.value,
                "stage": a.current_stage.value if a.current_stage else None,
                "started_at": a.started_at.isoformat() if a.started_at else None,
                "paused": bool(a.paused),
            }
            for a in rows
        ],
    }


@router.get("/logs/errors")
async def admin_error_logs(
    limit: int = 50,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Fetch recent error logs."""
    logs = (
        await db.execute(
            select(AnalysisLog)
            .where(AnalysisLog.level == "error")
            .order_by(AnalysisLog.timestamp.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "count": len(logs),
        "logs": [
            {
                "analysis_id": str(l.analysis_id),
                "timestamp": l.timestamp.isoformat(),
                "message": l.message,
                "stage": l.stage,
            }
            for l in logs
        ],
    }


@router.get("/users")
async def admin_list_users(
    skip: int = 0,
    limit: int = 100,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    )
    users = result.scalars().all()
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    return {
        "total": total,
        "users": [
            {
                "id": str(u.id),
                "email": u.email,
                "role": u.role.value if hasattr(u.role, "value") else str(u.role),
                "created_at": u.created_at.isoformat(),
                "updated_at": u.updated_at.isoformat(),
            }
            for u in users
        ],
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    payload: AdminUserCreate,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    existing = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="User with this email already exists")
    role = _parse_role(payload.role)
    user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    }


@router.patch("/users/{user_id}")
async def admin_update_user(
    user_id: UUID,
    payload: AdminUserUpdate,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.email:
        user.email = payload.email
    if payload.role:
        user.role = _parse_role(payload.role)
    if payload.password:
        user.hashed_password = get_password_hash(payload.password)
    await db.commit()
    await db.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    }


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: UUID,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    if str(user_id) == str(current_admin.id):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    return {"status": "deleted", "user_id": str(user_id)}


@router.get("/projects")
async def admin_list_projects(
    status_filter: str | None = None,
    skip: int = 0,
    limit: int = 100,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    stmt = (
        select(Project, User.email)
        .join(User, Project.owner_id == User.id)
        .order_by(Project.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if status_filter:
        try:
            status_enum = ProjectStatus(status_filter)
            stmt = stmt.where(Project.status == status_enum)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid project status")
    result = await db.execute(stmt)
    rows = result.all()
    total = (await db.execute(select(func.count()).select_from(Project))).scalar_one()
    return {
        "total": total,
        "projects": [
            {
                "id": str(p.id),
                "name": p.name,
                "owner_id": str(p.owner_id),
                "owner_email": owner_email or "",
                "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                "source_type": p.source_type.value if hasattr(p.source_type, "value") else str(p.source_type),
                "created_at": p.created_at.isoformat(),
            }
            for p, owner_email in rows
        ],
    }


@router.patch("/projects/{project_id}")
async def admin_update_project(
    project_id: UUID,
    payload: AdminProjectUpdate,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.status:
        try:
            project.status = ProjectStatus(payload.status)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid project status")
    await db.commit()
    await db.refresh(project)
    return {
        "id": str(project.id),
        "status": project.status.value if hasattr(project.status, "value") else str(project.status),
    }


@router.delete("/projects/{project_id}")
async def admin_delete_project(
    project_id: UUID,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.execute(delete(Project).where(Project.id == project_id))
    await db.commit()
    return {"status": "deleted", "project_id": str(project_id)}
