"""Authentication schemas"""
from pydantic import BaseModel, EmailStr
from uuid import UUID


class UserSignup(BaseModel):
    """User signup request"""
    email: EmailStr
    password: str
    role: str = "user"  # Default to user, admin can be set later


class UserLogin(BaseModel):
    """User login request"""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Token response"""
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """User response"""
    id: UUID
    email: str
    role: str
    
    class Config:
        from_attributes = True
