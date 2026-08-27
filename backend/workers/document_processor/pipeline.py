"""Document pipeline — routes each file type to its parser + chunker."""
from __future__ import annotations
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DocumentPipeline:
    async def process(self, document_id: str, file_path: str,
                      file_type: str, filename: str) -> list[dict]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info(f"Pipeline: {file_type} → {filename}")

        if file_type == "pdf":
            from workers.document_processor.parsers.pdf_parser import PDFParser
            parser = PDFParser()
            raw = await parser.parse(file_path)
        elif file_type in ("image", "screenshot"):
            from workers.document_processor.parsers.image_parser import ImageParser
            parser = ImageParser()
            raw = await parser.parse(file_path)
        elif file_type == "csv":
            from workers.document_processor.parsers.csv_parser import CSVParser
            parser = CSVParser()
            raw = await parser.parse(file_path)
        elif file_type == "log":
            from workers.document_processor.parsers.log_parser import LogParser
            parser = LogParser()
            raw = await parser.parse(file_path)
        elif file_type == "code":
            from workers.document_processor.parsers.code_parser import CodeParser
            ext = Path(filename).suffix.lstrip(".")
            parser = CodeParser(language=ext)
            raw = await parser.parse(file_path)
        else:  # text, markdown
            from workers.document_processor.parsers.text_parser import TextParser
            parser = TextParser()
            raw = await parser.parse(file_path)

        # Chunk the parsed content
        chunks = await self._chunk(raw, file_type, filename)
        return chunks

    async def _chunk(self, raw: dict, file_type: str, filename: str) -> list[dict]:
        chunks = []
        chunk_index = 0

        # Handle tables as separate chunks
        for tbl in raw.get("tables", []):
            from workers.document_processor.chunkers.table_chunker import TableChunker
            tc = TableChunker()
            for c in tc.chunk(tbl, chunk_index):
                chunks.append(c)
                chunk_index += 1

        # Handle code blocks
        for blk in raw.get("code_blocks", []):
            from workers.document_processor.chunkers.code_chunker import CodeChunker
            cc = CodeChunker()
            for c in cc.chunk(blk, chunk_index):
                chunks.append(c)
                chunk_index += 1

        # Handle main text
        text = raw.get("text", "")
        if text:
            if file_type == "log":
                from workers.document_processor.chunkers.temporal_chunker import TemporalChunker
                chunker = TemporalChunker()
            else:
                from workers.document_processor.chunkers.semantic_chunker import SemanticChunker
                chunker = SemanticChunker()

            for c in chunker.chunk(text, chunk_index, metadata=raw.get("metadata", {}),
                                   page_map=raw.get("page_map", {})):
                chunks.append(c)
                chunk_index += 1

        # Image description chunks (from image parsing)
        for desc in raw.get("image_descriptions", []):
            chunks.append({
                "chunk_index": chunk_index,
                "chunk_type": "image_description",
                "content": desc.get("description", ""),
                "page_number": desc.get("page_number"),
                "metadata": {"image_type": desc.get("image_type", "unknown"),
                             "source_image": desc.get("image_path", "")},
            })
            chunk_index += 1

        logger.info(f"Chunking produced {len(chunks)} chunks from {file_type} file")
        return chunks
