from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_url: str = "postgresql://contextbridge:contextbridge@postgres:5432/contextbridge"
    redis_url: str = "redis://redis:6379/0"
    qdrant_url: str = "http://qdrant:6333"

    class Config:
        env_file = ".env"


settings = Settings()
