from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_url: str = "postgresql://contextbridge:contextbridge@postgres:5432/contextbridge"
    redis_url: str = "redis://redis:6379/0"
    qdrant_url: str = "http://qdrant:6333"  # use http://localhost:6333 when running outside docker
    qdrant_collection: str = "contextbridge_kb"

    # Embeddings (jina-clip-v2: text + image in one shared space)
    embedding_model: str = "jinaai/jina-clip-v2"
    embedding_dim: int = 1024           # full size; Matryoshka allows truncating (e.g. 512)
    embedding_batch_size: int = 16
    embedding_device: str = "auto"      # auto | cpu | mps | cuda

    class Config:
        env_file = ".env"


settings = Settings()
