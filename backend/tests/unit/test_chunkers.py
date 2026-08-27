"""Unit tests for chunkers."""
import pytest
from workers.document_processor.chunkers.semantic_chunker import SemanticChunker
from workers.document_processor.chunkers.temporal_chunker import TemporalChunker
from workers.document_processor.chunkers.code_chunker import CodeChunker
from workers.document_processor.chunkers.table_chunker import TableChunker


class TestSemanticChunker:
    def test_basic_chunking(self):
        chunker = SemanticChunker()
        text = "First paragraph with some content.\n\nSecond paragraph here.\n\nThird paragraph."
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        assert all(c["chunk_type"] == "text" for c in chunks)
        assert all("content" in c for c in chunks)
        assert all("chunk_index" in c for c in chunks)

    def test_chunk_indices_sequential(self):
        chunker = SemanticChunker()
        text = "\n\n".join([f"Paragraph {i} " * 20 for i in range(10)])
        chunks = chunker.chunk(text, start_index=5)
        for i, c in enumerate(chunks):
            assert c["chunk_index"] == 5 + i

    def test_empty_text(self):
        chunker = SemanticChunker()
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []

    def test_long_paragraph_split(self):
        chunker = SemanticChunker()
        long_text = "word " * 800  # ~800 tokens
        chunks = chunker.chunk(long_text)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c["content"].split()) <= 700


class TestTemporalChunker:
    def test_timestamp_windowing(self):
        chunker = TemporalChunker()
        logs = "\n".join([
            f"2024-01-01T10:{i:02d}:00 INFO Service started" for i in range(60)
        ])
        chunks = chunker.chunk(logs)
        assert len(chunks) >= 2  # Should split across time windows

    def test_no_timestamp_fallback(self):
        chunker = TemporalChunker()
        text = "\n".join([f"plain log line {i}" for i in range(400)])
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        assert all(c["chunk_type"] == "log_window" for c in chunks)

    def test_max_lines_per_window(self):
        chunker = TemporalChunker()
        text = "\n".join([f"line {i}" for i in range(700)])
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2


class TestCodeChunker:
    def test_function_block(self):
        chunker = CodeChunker()
        block = {"block_type": "function", "content": "def foo():\n    return 42",
                 "code_language": "python", "start_line": 1, "end_line": 2}
        chunks = chunker.chunk(block)
        assert len(chunks) == 1
        assert chunks[0]["chunk_type"] == "code"
        assert chunks[0]["code_language"] == "python"

    def test_empty_block(self):
        chunker = CodeChunker()
        assert chunker.chunk({"block_type": "function", "content": ""}) == []


class TestTableChunker:
    def test_table_chunk(self):
        chunker = TableChunker()
        table = {"content": "col1 col2\nv1   v2", "page_number": 3, "table_index": 0}
        chunks = chunker.chunk(table)
        assert len(chunks) == 1
        assert chunks[0]["chunk_type"] == "table"
        assert chunks[0]["page_number"] == 3
