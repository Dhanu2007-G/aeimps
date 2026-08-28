FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libmagic1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --upgrade pip && \
    pip install fastapi sqlalchemy[asyncio] asyncpg alembic redis[hiredis] \
    qdrant-client neo4j anthropic langchain langchain-anthropic langgraph \
    sentence-transformers transformers torch numpy FlagEmbedding \
    pymupdf pillow pandas python-magic chardet unstructured \
    paddlepaddle paddleocr tree-sitter tree-sitter-python \
    opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc \
    pydantic pydantic-settings orjson aiofiles tenacity rapidfuzz spacy && \
    python -m spacy download en_core_web_sm

COPY . .
RUN mkdir -p /data/raw /data/models
