"""Authentication endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta
from src.database import get_db
from src.core.security import verify_password, get_password_hash, create_access_token
from src.core.config import settings
from src.core.logging_config import get_logger
from src.schemas.auth import UserSignup, UserLogin, Token, UserResponse
from src.models.user import User, UserRole
from src.core.exceptions import UnauthorizedException

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    user_data: UserSignup,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user"""
    logger.debug(f"Signup attempt for email: {user_data.email}")
    
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        logger.warning(f"Signup failed: Email already registered - {user_data.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Validate role
    try:
        role = UserRole(user_data.role.lower())
    except ValueError:
        logger.warning(f"Invalid role '{user_data.role}', defaulting to USER")
        role = UserRole.USER  # Default to user if invalid
    
    # Create new user
    try:
        hashed_password = get_password_hash(user_data.password)
        new_user = User(
            email=user_data.email,
            hashed_password=hashed_password,
            role=role
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        logger.info(f"User created: {new_user.email}")
        
        return UserResponse(
            id=new_user.id,
            email=new_user.email,
            role=new_user.role.value
        )
    except Exception as e:
        logger.error(f"Error creating user: {e}", exc_info=True)
        raise


@router.post("/login", response_model=Token)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate user and return access token"""
    logger.debug(f"Login attempt for email: {credentials.email}")
    
    # Find user
    result = await db.execute(
        select(User).where(User.email == credentials.email)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(credentials.password, user.hashed_password):
        logger.warning(f"Login failed: Invalid credentials for email: {credentials.email}")
        raise UnauthorizedException("Incorrect email or password")
    
    # Create access token
    try:
        access_token = create_access_token(
            # python-jose enforces `sub` to be a string
            data={"sub": str(user.id), "email": user.email, "role": user.role.value}
        )
        logger.info(f"Login successful: {user.email}")
        return Token(access_token=access_token)
    except Exception as e:
        logger.error(f"Error creating access token: {e}", exc_info=True)
        raise
