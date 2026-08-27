FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl libmagic1 libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --upgrade pip && \
    pip install -e ".[dev]" || pip install fastapi uvicorn[standard] \
    sqlalchemy[asyncio] asyncpg alembic redis[hiredis] \
    qdrant-client neo4j anthropic langchain langchain-anthropic langgraph \
    sentence-transformers transformers torch numpy \
    pymupdf pillow pandas python-magic chardet unstructured \
    opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi \
    opentelemetry-exporter-otlp-proto-grpc prometheus-fastapi-instrumentator \
    pydantic pydantic-settings orjson aiofiles httpx tenacity jinja2 \
    python-multipart passlib[bcrypt] rapidfuzz spacy && \
    python -m spacy download en_core_web_sm

COPY . .

RUN mkdir -p /data/raw /data/models

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--loop", "uvloop", "--http", "httptools"]
