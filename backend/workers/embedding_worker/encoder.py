"""
BGE Embedding Encoder
Supports BAAI/bge-large-en-v1.5 (dense) and BAAI/bge-m3 (sparse+dense).
Falls back to random vectors when MOCK_MODELS=true (dev/CI environments).
"""
from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


class BGEEncoder:
    """
    Production embedding encoder using BGE models.
    Handles batching, GPU/CPU selection, and model caching.
    """

    def __init__(self):
        self._dense_model = None
        self._sparse_model = None
        self._reranker = None
        self._device = None
        self._initialized = False

    def _get_device(self) -> str:
        if self._device is None:
            try:
                import torch
                if torch.cuda.is_available():
                    self._device = "cuda"
                    logger.info("Using GPU for embeddings")
                else:
                    self._device = "cpu"
                    logger.info("Using CPU for embeddings (no GPU detected)")
            except Exception:
                self._device = "cpu"
        return self._device

    def _load_dense_model(self):
        if self._dense_model is not None:
            return self._dense_model

        if settings.MOCK_MODELS:
            logger.info("MOCK_MODELS=true — using random vectors for dense embeddings")
            return None

        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading dense model: {settings.EMBEDDING_MODEL}")
            start = time.monotonic()
            self._dense_model = SentenceTransformer(
                settings.EMBEDDING_MODEL,
                device=self._get_device(),
                cache_folder=settings.MODEL_CACHE_PATH,
            )
            logger.info(f"Dense model loaded in {time.monotonic()-start:.1f}s")
        except Exception as e:
            logger.error(f"Failed to load dense model: {e}")
            logger.warning("Falling back to mock embeddings")
        return self._dense_model

    def _load_reranker(self):
        if self._reranker is not None:
            return self._reranker

        if settings.MOCK_MODELS:
            return None

        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading reranker: {settings.RERANKER_MODEL}")
            self._reranker = CrossEncoder(
                settings.RERANKER_MODEL,
                device=self._get_device(),
                max_length=512,
            )
        except Exception as e:
            logger.error(f"Failed to load reranker: {e}")
        return self._reranker

    def encode_dense(
        self,
        texts: list[str],
        batch_size: int | None = None,
        normalize: bool = True,
    ) -> list[list[float]]:
        """Encode texts to dense vectors using BGE-large."""
        if not texts:
            return []

        batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        model = self._load_dense_model()

        if model is None:
            # Mock: return random normalized vectors
            vecs = np.random.randn(len(texts), settings.EMBEDDING_DIM).astype(np.float32)
            if normalize:
                norms = np.linalg.norm(vecs, axis=1, keepdims=True)
                vecs = vecs / np.maximum(norms, 1e-8)
            return vecs.tolist()

        # BGE-specific: prepend query instruction for query encoding
        # For document encoding, no prefix needed
        try:
            embeddings = model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=normalize,
                show_progress_bar=len(texts) > 100,
                convert_to_numpy=True,
            )
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Dense encoding failed: {e}")
            vecs = np.random.randn(len(texts), settings.EMBEDDING_DIM).astype(np.float32)
            return vecs.tolist()

    def encode_query(self, query: str) -> list[float]:
        """Encode a query with BGE instruction prefix for retrieval."""
        # BGE models benefit from this instruction prefix for queries
        instruction_query = f"Represent this sentence for searching relevant passages: {query}"
        result = self.encode_dense([instruction_query])
        return result[0] if result else []

    def encode_sparse(
        self,
        texts: list[str],
    ) -> list[dict[int, float]]:
        """
        Encode texts to sparse vectors using BGE-M3.
        Returns list of {token_id: weight} dicts for Qdrant sparse vectors.
        """
        if not texts:
            return []

        if settings.MOCK_MODELS:
            # Mock sparse vectors: random sparse representation
            results = []
            for _ in texts:
                n_nonzero = np.random.randint(10, 50)
                indices = np.random.choice(30000, n_nonzero, replace=False)
                weights = np.abs(np.random.randn(n_nonzero)).tolist()
                results.append({int(idx): float(w) for idx, w in zip(indices, weights)})
            return results

        try:
            from FlagEmbedding import BGEM3FlagModel
            if not hasattr(self, '_bgem3'):
                logger.info(f"Loading BGE-M3 for sparse encoding: {settings.SPARSE_MODEL}")
                self._bgem3 = BGEM3FlagModel(
                    settings.SPARSE_MODEL,
                    use_fp16=True,
                    device=self._get_device(),
                )

            outputs = self._bgem3.encode(
                texts,
                batch_size=settings.EMBEDDING_BATCH_SIZE,
                return_dense=False,
                return_sparse=True,
                return_colbert_vecs=False,
            )
            sparse_vecs = outputs["lexical_weights"]
            return [dict(sv) for sv in sparse_vecs]

        except ImportError:
            logger.warning("FlagEmbedding not available — using mock sparse vectors")
        except Exception as e:
            logger.error(f"Sparse encoding failed: {e}")

        # Fallback mock
        return [
            {int(i): float(np.abs(np.random.randn()))
             for i in np.random.choice(30000, 20, replace=False)}
            for _ in texts
        ]

    def rerank(
        self,
        query: str,
        passages: list[str],
    ) -> list[float]:
        """
        Cross-encoder reranking: scores (query, passage) pairs.
        Returns list of relevance scores aligned with passages list.
        """
        if not passages:
            return []

        reranker = self._load_reranker()
        if reranker is None:
            # Mock: return random scores sorted descending
            return [float(s) for s in np.random.rand(len(passages))]

        try:
            pairs = [(query, p) for p in passages]
            scores = reranker.predict(pairs, batch_size=16)
            return [float(s) for s in scores]
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return [float(s) for s in np.random.rand(len(passages))]


# Module-level singleton (loaded once per worker process)
_encoder: BGEEncoder | None = None


def get_encoder() -> BGEEncoder:
    global _encoder
    if _encoder is None:
        _encoder = BGEEncoder()
    return _encoder
