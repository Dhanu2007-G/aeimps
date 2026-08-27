"""
Semantic Chunker — paragraph + section-aware chunking.
Respects document structure rather than blindly splitting on token count.
"""
from __future__ import annotations
import re
import logging

logger = logging.getLogger(__name__)

MAX_CHUNK_TOKENS = 600
MIN_CHUNK_TOKENS = 80
APPROX_CHARS_PER_TOKEN = 4


class SemanticChunker:
    def chunk(
        self,
        text: str,
        start_index: int = 0,
        metadata: dict | None = None,
        page_map: dict | None = None,
    ) -> list[dict]:
        metadata = metadata or {}
        page_map = page_map or {}
        chunks = []
        index = start_index

        # Split on section headers first (markdown ## or ALL CAPS lines)
        sections = self._split_sections(text)

        for section_title, section_text in sections:
            # Split section into paragraphs
            paragraphs = [p.strip() for p in re.split(r"\n{2,}", section_text) if p.strip()]

            current_chunk = []
            current_tokens = 0
            current_page = self._get_page(text, section_text, page_map)

            for para in paragraphs:
                para_tokens = len(para) // APPROX_CHARS_PER_TOKEN

                # If paragraph itself is too long, split by sentences
                if para_tokens > MAX_CHUNK_TOKENS:
                    if current_chunk:
                        chunks.append(self._make_chunk(
                            index, " ".join(current_chunk),
                            current_page, section_title, metadata
                        ))
                        index += 1
                        current_chunk, current_tokens = [], 0

                    for sent_chunk in self._split_long_paragraph(para):
                        chunks.append(self._make_chunk(
                            index, sent_chunk, current_page, section_title, metadata
                        ))
                        index += 1
                    continue

                if current_tokens + para_tokens > MAX_CHUNK_TOKENS and current_chunk:
                    chunks.append(self._make_chunk(
                        index, " ".join(current_chunk),
                        current_page, section_title, metadata
                    ))
                    index += 1
                    current_chunk, current_tokens = [], 0

                current_chunk.append(para)
                current_tokens += para_tokens

            if current_chunk and current_tokens >= MIN_CHUNK_TOKENS:
                chunks.append(self._make_chunk(
                    index, " ".join(current_chunk),
                    current_page, section_title, metadata
                ))
                index += 1

        return chunks

    def _split_sections(self, text: str) -> list[tuple[str, str]]:
        section_pattern = re.compile(r'^(#{1,3}\s+.+|[A-Z][A-Z\s]{5,}:?\s*)$', re.MULTILINE)
        positions = [(m.start(), m.group()) for m in section_pattern.finditer(text)]

        if not positions:
            return [("", text)]

        sections = []
        for i, (pos, title) in enumerate(positions):
            end = positions[i+1][0] if i+1 < len(positions) else len(text)
            section_text = text[pos + len(title):end]
            if section_text.strip():
                sections.append((title.strip(), section_text))

        if not sections:
            return [("", text)]
        return sections

    def _split_long_paragraph(self, text: str) -> list[str]:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks, current, tokens = [], [], 0
        for sent in sentences:
            t = len(sent) // APPROX_CHARS_PER_TOKEN
            if tokens + t > MAX_CHUNK_TOKENS and current:
                chunks.append(" ".join(current))
                current, tokens = [], 0
            current.append(sent)
            tokens += t
        if current:
            chunks.append(" ".join(current))
        return chunks

    def _get_page(self, full_text: str, section_text: str, page_map: dict) -> int | None:
        if not page_map:
            return None
        try:
            offset = full_text.find(section_text[:50])
            pages = [p for off, p in sorted(page_map.items()) if off <= offset]
            return pages[-1] if pages else None
        except Exception:
            return None

    def _make_chunk(self, index: int, content: str, page: int | None,
                    section: str, metadata: dict) -> dict:
        return {
            "chunk_index": index,
            "chunk_type": "text",
            "content": content.strip(),
            "token_count": len(content) // APPROX_CHARS_PER_TOKEN,
            "page_number": page,
            "metadata": {**metadata, "section": section[:100] if section else None},
        }
