"""Admin schemas for user/project management."""
from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str = "user"  # user or admin


class AdminUserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None  # user or admin


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    role: str
    created_at: str
    updated_at: str


class AdminProjectUpdate(BaseModel):
    status: Optional[str] = None

