"""Initialize database - create tables"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import init_db, close_db
from src.core.logging_config import setup_logging

# Set up logger
logger = setup_logging("macad.init_db", log_file="init_db.log")


async def main():
    """Initialize database"""
    logger.info("Initializing database...")
    try:
        await init_db()
        logger.info("Database initialized successfully!")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
