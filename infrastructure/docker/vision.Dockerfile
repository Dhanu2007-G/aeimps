FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1     PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends     build-essential libgl1 libglib2.0-0 libmagic1     && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --upgrade pip &&     pip install transformers accelerate pillow     qwen-vl-utils redis[hiredis] sqlalchemy[asyncio] asyncpg     qdrant-client pydantic pydantic-settings orjson tenacity     opentelemetry-api opentelemetry-sdk sentence-transformers

COPY . .
RUN mkdir -p /data/raw /data/models
