"""Application configuration"""
from pydantic_settings import BaseSettings
from typing import Optional
from urllib.parse import quote_plus
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database Configuration (separate fields)
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "macad_db"
    
    @property
    def DATABASE_URL(self) -> str:
        """Construct async database URL from separate fields"""
        password = quote_plus(self.DB_PASSWORD)
        return f"postgresql+asyncpg://{self.DB_USER}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Construct sync database URL for Alembic"""
        password = quote_plus(self.DB_PASSWORD)
        return f"postgresql://{self.DB_USER}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    # JWT Security
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Application
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "maCAD System"
    DEBUG: bool = True
    
    # File Storage
    STORAGE_PATH: str = "./storage"
    MAX_ZIP_SIZE_MB: int = 100
    
    # GitHub (for future use)
    GITHUB_TOKEN: Optional[str] = None
    
    # LLM (for future milestones)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-5.2"
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # Langfuse (for future milestones)
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    # Accept either LANGFUSE_HOST or LANGFUSE_BASE_URL from env
    LANGFUSE_HOST: Optional[str] = None
    LANGFUSE_BASE_URL: Optional[str] = None

    @property
    def LANGFUSE_HOST_RESOLVED(self) -> str:
        return self.LANGFUSE_HOST or self.LANGFUSE_BASE_URL or "https://cloud.langfuse.com"

    # MCP (FastMCP server URL for conditional web search)
    MCP_SERVER_URL: Optional[str] = None

    # Pause timeout (minutes) before auto-cancel
    PAUSE_TIMEOUT_MINUTES: int = 5
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields in .env that aren't defined in Settings


# Global settings instance
settings = Settings()

# Ensure storage directory exists
os.makedirs(settings.STORAGE_PATH, exist_ok=True)
os.makedirs(os.path.join(settings.STORAGE_PATH, "projects"), exist_ok=True)
os.makedirs(os.path.join(settings.STORAGE_PATH, "uploads"), exist_ok=True)
