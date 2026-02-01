"""Seed admin user"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import AsyncSessionLocal
from src.models.user import User, UserRole
from src.core.security import get_password_hash
from src.core.logging_config import setup_logging

# Set up logger
logger = setup_logging("macad.seed_admin", log_file="seed_admin.log")


async def create_admin(email: str, password: str):
    """Create admin user"""
    try:
        async with AsyncSessionLocal() as db:
            # Check if admin exists
            from sqlalchemy import select
            result = await db.execute(
                select(User).where(User.email == email)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                logger.warning(f"User with email {email} already exists!")
                return
            
            # Create admin
            admin = User(
                email=email,
                hashed_password=get_password_hash(password),
                role=UserRole.ADMIN
            )
            db.add(admin)
            await db.commit()
            logger.info(f"Admin user created successfully: {email}")
    except Exception as e:
        logger.error(f"Failed to create admin user: {e}", exc_info=True)
        raise


async def main():
    """Main function"""
    if len(sys.argv) < 3:
        logger.error("Usage: python scripts/seed_admin.py <email> <password>")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    
    logger.info(f"Creating admin user: {email}")
    await create_admin(email, password)


if __name__ == "__main__":
    asyncio.run(main())
