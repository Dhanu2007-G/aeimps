"""Unit tests for retrieval fusion and reranking."""
import pytest
from app.services.retrieval.fusion import RRFFusion
from app.services.retrieval.orchestrator import ChunkResult


def _make_chunk(cid, score=0.5, doc_id="doc1"):
    return ChunkResult(chunk_id=cid, document_id=doc_id, content=f"Content {cid}",
                       chunk_type="text", score=score)


class TestRRFFusion:
    def setup_method(self):
        self.fusion = RRFFusion(k=60)

    def test_empty_inputs(self):
        assert self.fusion.fuse([]) == []
        assert self.fusion.fuse([[]]) == []

    def test_single_list(self):
        chunks = [_make_chunk(f"c{i}", 1.0 - i * 0.1) for i in range(5)]
        result = self.fusion.fuse([chunks])
        assert len(result) == 5

    def test_deduplication_across_lists(self):
        list1 = [_make_chunk("c1"), _make_chunk("c2"), _make_chunk("c3")]
        list2 = [_make_chunk("c2"), _make_chunk("c3"), _make_chunk("c4")]
        result = self.fusion.fuse([list1, list2])
        ids = [r.chunk_id for r in result]
        assert len(ids) == len(set(ids)), "Duplicates found"
        assert len(result) == 4

    def test_consensus_boost(self):
        """Chunk appearing in all lists should rank higher."""
        shared = _make_chunk("shared")
        list1 = [shared, _make_chunk("a1"), _make_chunk("a2")]
        list2 = [_make_chunk("b1"), shared, _make_chunk("b2")]
        list3 = [_make_chunk("c1"), _make_chunk("c2"), shared]
        result = self.fusion.fuse([list1, list2, list3])
        assert result[0].chunk_id == "shared"

    def test_rrf_score_formula(self):
        """Verify RRF score: 1/(k+rank)."""
        chunk = _make_chunk("x")
        result = self.fusion.fuse([[chunk]])
        expected = 1.0 / (60 + 1)
        assert abs(result[0].score - expected) < 1e-9

    def test_order_preservation(self):
        """Higher-ranked chunks in input should get better RRF scores."""
        chunks = [_make_chunk(f"c{i}") for i in range(10)]
        result = self.fusion.fuse([chunks])
        # c0 was rank 1 → highest RRF score
        assert result[0].chunk_id == "c0"

    def test_four_list_fusion(self):
        lists = [
            [_make_chunk("a"), _make_chunk("b"), _make_chunk("c")],
            [_make_chunk("b"), _make_chunk("d"), _make_chunk("e")],
            [_make_chunk("c"), _make_chunk("b"), _make_chunk("f")],
            [_make_chunk("a"), _make_chunk("g"), _make_chunk("b")],
        ]
        result = self.fusion.fuse(lists)
        # "b" appears in all 4 lists → should be top
        assert result[0].chunk_id == "b"


class TestReranker:
    def test_reranker_sorts_by_score(self, mock_encoder, monkeypatch):
        import asyncio
        from app.services.retrieval.reranker import BGEReranker
        monkeypatch.setattr("workers.embedding_worker.encoder.get_encoder", lambda: mock_encoder)

        chunks = [_make_chunk(f"c{i}", score=0.5) for i in range(5)]
        reranker = BGEReranker()
        result = asyncio.get_event_loop().run_until_complete(
            reranker.rerank("test query", chunks)
        )
        scores = [r.score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_empty_input(self):
        import asyncio
        from app.services.retrieval.reranker import BGEReranker
        result = asyncio.get_event_loop().run_until_complete(
            BGEReranker().rerank("query", [])
        )
        assert result == []
