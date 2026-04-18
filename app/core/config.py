from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "TaskOrchestrator"
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/taskdb"
    DATABASE_SYNC_URL: str = "postgresql://postgres:postgres@localhost:5432/taskdb"

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    SECRET_KEY: str = "change_this_secret"
    API_KEY: str = "dev-api-key"

    CELERY_MAX_RETRIES: int = 3
    CELERY_RETRY_BACKOFF: int = 60
    TASK_SOFT_TIME_LIMIT: int = 300
    TASK_TIME_LIMIT: int = 600

    FLOWER_PORT: int = 5555
    FLOWER_BASIC_AUTH: str = "admin:admin"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
