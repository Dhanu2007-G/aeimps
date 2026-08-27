"""Unit tests for document parsers."""
import pytest
import asyncio
import tempfile
import os


class TestCSVParser:
    def test_basic_csv(self):
        from workers.document_processor.parsers.csv_parser import CSVParser

        content = "name,age,city\nAlice,30,NYC\nBob,25,LA\nCarol,35,Chicago\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(content)
            path = f.name

        try:
            parser = CSVParser()
            result = asyncio.get_event_loop().run_until_complete(parser.parse(path))
            assert "text" in result
            assert "name" in result["text"]
            assert result["metadata"]["row_count"] == 3
            assert result["metadata"]["column_count"] == 3
        finally:
            os.unlink(path)


class TestLogParser:
    def test_json_log_detection(self):
        from workers.document_processor.parsers.log_parser import LogParser

        lines = ['{"level": "ERROR", "msg": "connection failed", "ts": "2024-01-01T10:00:00"}'] * 5
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("\n".join(lines))
            path = f.name

        try:
            parser = LogParser()
            result = asyncio.get_event_loop().run_until_complete(parser.parse(path))
            assert result["metadata"]["log_format"] == "json"
        finally:
            os.unlink(path)

    def test_severity_counting(self):
        from workers.document_processor.parsers.log_parser import LogParser

        content = "ERROR: something failed\nWARN: degraded\nINFO: started\nERROR: again\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write(content)
            path = f.name

        try:
            parser = LogParser()
            result = asyncio.get_event_loop().run_until_complete(parser.parse(path))
            counts = result["metadata"]["severity_counts"]
            assert counts["ERROR"] >= 2
        finally:
            os.unlink(path)


class TestTextParser:
    def test_plain_text(self):
        from workers.document_processor.parsers.text_parser import TextParser

        content = "This is a test document.\nWith multiple lines.\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(content)
            path = f.name

        try:
            parser = TextParser()
            result = asyncio.get_event_loop().run_until_complete(parser.parse(path))
            assert "text" in result
            assert "test document" in result["text"]
        finally:
            os.unlink(path)
