"""Shared pytest fixtures for AEIMPS test suite."""
import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_encoder():
    """Mock BGE encoder returning deterministic vectors."""
    import numpy as np
    enc = MagicMock()
    enc.encode_dense = lambda texts, **kw: [
        np.random.default_rng(hash(t) % 2**32).standard_normal(1024).tolist()
        for t in texts
    ]
    enc.encode_query = lambda q: np.random.default_rng(42).standard_normal(1024).tolist()
    enc.encode_sparse = lambda texts: [
        {i: float(v) for i, v in enumerate(np.abs(np.random.default_rng(j).standard_normal(20)))}
        for j, _ in enumerate(texts)
    ]
    enc.rerank = lambda query, passages: [float(i / len(passages)) for i in range(len(passages), 0, -1)]
    return enc


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    llm = AsyncMock()
    llm.complete.return_value = ("Mock LLM response", 100)
    llm.complete_structured.return_value = ({"answer": "Mock answer", "confidence": 0.8}, 100)
    return llm


@pytest.fixture
def sample_chunks():
    return [
        {
            "chunk_id": f"chunk-{i}",
            "document_id": "doc-1",
            "content": f"Sample content about payment service incident #{i}. "
                       "The auth service caused a cascade failure.",
            "chunk_type": "text",
            "score": 0.9 - i * 0.05,
            "source_doc": {"filename": "runbook.md", "original_name": "Runbook", "doc_type": "markdown"},
            "metadata": {},
        }
        for i in range(5)
    ]
