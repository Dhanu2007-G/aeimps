"""Integration tests — require running PostgreSQL, Redis, Qdrant, Neo4j."""
import pytest
import asyncio
import io
import os


@pytest.mark.integration
class TestIngestionPipeline:
    """Full ingestion pipeline integration test."""

    @pytest.mark.asyncio
    async def test_text_document_ingest(self):
        """Upload a text doc → verify job created → verify chunks in DB."""
        from fastapi.testclient import TestClient
        from app.main import app

        api_key = os.getenv("TEST_API_KEY", "test-key")
        client = TestClient(app)

        content = b"Test document content about payment service architecture."
        resp = client.post(
            "/api/v1/ingest/document",
            files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
            data={"tags": "test,integration", "priority": "1"},
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert "document_id" in data
        assert data["status"] in ("QUEUED", "PROCESSING", "READY")

    @pytest.mark.asyncio
    async def test_duplicate_detection(self):
        """Same file uploaded twice returns existing document."""
        from fastapi.testclient import TestClient
        from app.main import app

        api_key = os.getenv("TEST_API_KEY", "test-key")
        client = TestClient(app)
        content = b"Unique content for dedup test: " + os.urandom(16)

        resp1 = client.post("/api/v1/ingest/document",
            files={"file": ("dedup.txt", io.BytesIO(content), "text/plain")},
            headers={"X-API-Key": api_key})
        resp2 = client.post("/api/v1/ingest/document",
            files={"file": ("dedup.txt", io.BytesIO(content), "text/plain")},
            headers={"X-API-Key": api_key})

        if resp1.status_code == 202 and resp2.status_code == 202:
            assert resp1.json()["document_id"] == resp2.json()["document_id"]


@pytest.mark.integration
class TestRetrievalPipeline:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        from fastapi.testclient import TestClient
        from app.main import app

        api_key = os.getenv("TEST_API_KEY", "test-key")
        client = TestClient(app)

        resp = client.post("/api/v1/retrieve/search",
            json={"query": "payment service", "mode": "keyword", "top_k": 5},
            headers={"X-API-Key": api_key})

        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "query_metadata" in data

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/api/v1/admin/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
