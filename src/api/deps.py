"""API dependencies"""
from typing import Optional
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database import get_db
from src.core.security import decode_access_token
from src.core.logging_config import get_logger
from src.models.user import User, UserRole
from src.core.exceptions import UnauthorizedException, ForbiddenException

logger = get_logger(__name__)
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user"""
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if payload is None:
        raise UnauthorizedException("Invalid authentication credentials")
    
    raw_user_id = payload.get("sub")
    if raw_user_id is None:
        raise UnauthorizedException("Invalid authentication credentials")
    
    try:
        # Try to parse as UUID
        user_id = UUID(raw_user_id)
    except (TypeError, ValueError):
        raise UnauthorizedException("Invalid authentication credentials")
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise UnauthorizedException("User not found")
    
    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current user and verify admin role (case-insensitive: admin, ADMIN)."""
    role_str = (getattr(current_user.role, "value", None) or str(current_user.role)).strip().upper()
    if role_str != "ADMIN":
        logger.warning(f"Admin access denied for user {current_user.id} (role={role_str})")
        raise ForbiddenException("Admin access required")
    return current_user


async def get_current_user_from_token(token: str, db: AsyncSession) -> User:
    """Extract and validate user from bearer token (useful for WebSocket)"""
    payload = decode_access_token(token)
    
    if payload is None:
        raise UnauthorizedException("Invalid authentication credentials")
    
    raw_user_id = payload.get("sub")
    if raw_user_id is None:
        raise UnauthorizedException("Invalid authentication credentials")
    
    try:
        # Try to parse as UUID
        user_id = UUID(raw_user_id)
    except (TypeError, ValueError):
        raise UnauthorizedException("Invalid authentication credentials")
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise UnauthorizedException("User not found")
    
    return user
