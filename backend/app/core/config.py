"""
AEIMPS Core Configuration
All settings driven from environment variables with validation.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def read_secret(secret_name: str, default: str | None = None) -> str | None:
    """Read secret from file (Docker Secrets) or environment variable."""
    # Try reading from Docker secret file
    secret_file = Path(f"/run/secrets/{secret_name}")
    if secret_file.exists():
        return secret_file.read_text().strip()
    
    # Try reading from custom secret file path (env var with _FILE suffix)
    file_path_env = os.getenv(f"{secret_name.upper()}_FILE")
    if file_path_env:
        file_path = Path(file_path_env)
        if file_path.exists():
            return file_path.read_text().strip()
    
    # Fall back to environment variable
    env_value = os.getenv(secret_name.upper())
    if env_value:
        return env_value
    
    return default


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Core ────────────────────────────────────────────────
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    SECRET_KEY: str = Field(..., min_length=32)
    APP_NAME: str = "AEIMPS"
    APP_VERSION: str = "1.0.0"
    APP_URL: str = "http://localhost:8000"  # Base URL for SAML and other integrations
    PORT: int = 8000
    WORKERS: int = 4

    # ─── PostgreSQL ──────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://aeimps:aeimps_secret@localhost:5432/aeimps"
    )
    DATABASE_URL_SYNC: str = Field(
        default="postgresql://aeimps:aeimps_secret@localhost:5432/aeimps"
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # ─── Redis ───────────────────────────────────────────────
    REDIS_URL: str = "redis://:redis_secret@localhost:6379/0"
    REDIS_STREAM_MAX_LEN: int = 10000
    REDIS_WORKER_BLOCK_MS: int = 5000

    # ─── Qdrant ──────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_CHUNKS: str = "document_chunks"
    QDRANT_COLLECTION_IMAGES: str = "image_features"
    QDRANT_COLLECTION_ENTITIES: str = "entity_embeddings"

    # ─── Neo4j ───────────────────────────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j_secret"
    NEO4J_DATABASE: str = "neo4j"

    # ─── Anthropic ───────────────────────────────────────────
    ANTHROPIC_API_KEY: str | None = None
    CLAUDE_MODEL: str = "claude-sonnet-4-5"
    CLAUDE_MAX_TOKENS: int = 4096
    CLAUDE_TEMPERATURE: float = 0.1

    # ─── Embedding Models ────────────────────────────────────
    MOCK_MODELS: bool = False
    EMBEDDING_MODEL: str = "BAAI/bge-large-en-v1.5"
    EMBEDDING_DIM: int = 1024
    SPARSE_MODEL: str = "BAAI/bge-m3"
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    EMBEDDING_BATCH_SIZE: int = 32

    # ─── Vision ──────────────────────────────────────────────
    VISION_MODEL: str = "Qwen/Qwen2-VL-7B-Instruct"
    VISION_MAX_IMAGE_SIZE: int = 2048

    # ─── File Storage ────────────────────────────────────────
    MAX_FILE_SIZE_MB: int = 100
    RAW_FILES_PATH: str = "/data/raw"
    MODEL_CACHE_PATH: str = "/data/models"
    ALLOWED_EXTENSIONS: set[str] = {
        "pdf", "png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp",
        "txt", "md", "csv", "log", "py", "js", "ts", "go", "java",
        "rs", "cpp", "c", "h", "yaml", "yml", "json", "toml",
    }

    # ─── Redis Streams ───────────────────────────────────────
    STREAM_INGEST: str = "stream:doc.ingest"
    STREAM_EMBED: str = "stream:embed.queue"
    STREAM_KG: str = "stream:kg.queue"
    STREAM_VISION: str = "stream:vision.queue"
    STREAM_DLQ: str = "stream:dlq"

    # ─── Authentication ──────────────────────────────────────
    JWT_SECRET_KEY: str | None = None  # Falls back to SECRET_KEY if not set
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 24
    
    # ─── Rate Limiting ───────────────────────────────────────
    DEFAULT_RATE_LIMIT_RPM: int = 60
    RATE_LIMIT_WINDOW: int = 60

    # ─── Agent ───────────────────────────────────────────────
    AGENT_MAX_ITERATIONS: int = 8
    AGENT_MIN_CONFIDENCE: float = 0.65
    AGENT_SESSION_TTL_HOURS: int = 24

    # ─── Retrieval ───────────────────────────────────────────
    RETRIEVAL_TOP_K: int = 8
    RETRIEVAL_CANDIDATES: int = 40
    RRF_K: int = 60
    RERANKER_ENABLED: bool = True

    # ─── Evaluation ──────────────────────────────────────────
    EVAL_MIN_FAITHFULNESS: float = 0.75
    EVAL_MIN_OVERALL: float = 0.65
    EVAL_ENABLED: bool = True

    # ─── Observability ───────────────────────────────────────
    OTEL_SERVICE_NAME: str = "aeimps"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://otel-collector:4317"
    METRICS_ENABLED: bool = True

    @field_validator("ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def parse_extensions(cls, v: str | set) -> set[str]:
        if isinstance(v, str):
            return set(v.split(","))
        return v

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024
    
    @property
    def jwt_secret(self) -> str:
        """Get JWT secret key, falling back to SECRET_KEY if not set."""
        return self.JWT_SECRET_KEY or self.SECRET_KEY


@lru_cache
def get_settings() -> Settings:
    """Get settings singleton with secrets loaded."""
    settings = Settings()
    
    # Override with secrets from files if available
    if secret_key := read_secret("secret_key"):
        settings.SECRET_KEY = secret_key
    if postgres_pass := read_secret("postgres_password"):
        # Update DATABASE_URL with secret
        settings.DATABASE_URL = settings.DATABASE_URL.replace(
            settings.DATABASE_URL.split(":")[2].split("@")[0], postgres_pass
        )
        settings.DATABASE_URL_SYNC = settings.DATABASE_URL_SYNC.replace(
            settings.DATABASE_URL_SYNC.split(":")[2].split("@")[0], postgres_pass
        )
    if redis_pass := read_secret("redis_password"):
        settings.REDIS_URL = f"redis://:{redis_pass}@{settings.REDIS_URL.split('@')[1]}"
    if neo4j_pass := read_secret("neo4j_password"):
        settings.NEO4J_PASSWORD = neo4j_pass
    if anthropic_key := read_secret("anthropic_api_key"):
        settings.ANTHROPIC_API_KEY = anthropic_key
    
    return settings


settings = get_settings()
