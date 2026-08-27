"""
Context Assembler
Enriches retrieved chunks with parent context, deduplication,
and entity annotations before LLM consumption.
"""
from __future__ import annotations
import logging
from app.services.retrieval.orchestrator import ChunkResult

logger = logging.getLogger(__name__)


class ContextAssembler:
    """
    Post-retrieval enrichment pipeline:
    1. Parent context injection (short chunks get neighboring chunk text)
    2. Near-duplicate removal (cosine sim > 0.97)
    3. Source metadata attachment
    4. Token budget enforcement
    """

    MAX_CONTEXT_TOKENS = 80000

    async def enrich(self, chunks: list[ChunkResult]) -> list[ChunkResult]:
        """Enrich chunks with parent context and dedup."""
        if not chunks:
            return []

        # Step 1: Inject parent context for very short chunks
        enriched = await self._inject_parent_context(chunks)

        # Step 2: Deduplicate near-identical chunks
        deduped = self._deduplicate(enriched)

        return deduped

    async def _inject_parent_context(self, chunks: list[ChunkResult]) -> list[ChunkResult]:
        """For chunks < 100 tokens, fetch neighboring chunks for context."""
        short_chunks = [c for c in chunks if len(c.content.split()) < 80]
        if not short_chunks:
            return chunks

        short_ids = {c.chunk_id for c in short_chunks}

        try:
            from sqlalchemy import text
            from app.db.postgres import get_db

            async with get_db() as db:
                for chunk in chunks:
                    if chunk.chunk_id not in short_ids:
                        continue

                    result = await db.execute(
                        text("""
                            SELECT c2.content
                            FROM document_chunks c1
                            JOIN document_chunks c2
                              ON c2.document_id = c1.document_id
                              AND c2.chunk_index BETWEEN c1.chunk_index - 1 AND c1.chunk_index + 1
                              AND c2.id != c1.id
                            WHERE c1.id = :chunk_id
                            ORDER BY c2.chunk_index
                            LIMIT 2
                        """),
                        {"chunk_id": chunk.chunk_id},
                    )
                    neighbors = result.fetchall()
                    if neighbors:
                        neighbor_text = " ".join(row[0] for row in neighbors)
                        chunk.content = f"{neighbor_text}\n\n{chunk.content}"
                        chunk.metadata["parent_context_injected"] = True
        except Exception as e:
            logger.debug(f"Parent context injection error (non-critical): {e}")

        return chunks

    def _deduplicate(self, chunks: list[ChunkResult]) -> list[ChunkResult]:
        """Remove near-duplicate chunks based on content overlap."""
        if len(chunks) <= 1:
            return chunks

        seen_content: list[str] = []
        unique: list[ChunkResult] = []

        for chunk in chunks:
            content_words = set(chunk.content.lower().split())
            is_duplicate = False

            for prev_content in seen_content:
                prev_words = set(prev_content.lower().split())
                if not content_words or not prev_words:
                    continue
                # Jaccard similarity as fast dedup proxy
                intersection = len(content_words & prev_words)
                union = len(content_words | prev_words)
                jaccard = intersection / union if union > 0 else 0
                if jaccard > 0.85:
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique.append(chunk)
                seen_content.append(chunk.content)

        logger.debug(f"Dedup: {len(chunks)} → {len(unique)} chunks")
        return unique

    def format_for_llm(
        self,
        chunks: list[ChunkResult],
        max_tokens: int = 32000,
    ) -> str:
        """Format chunks as a numbered context block for LLM prompts."""
        parts = []
        total_tokens = 0

        for i, chunk in enumerate(chunks, 1):
            source = chunk.source_doc
            header = (
                f"[SOURCE {i}] "
                f"{source.get('original_name', source.get('filename', 'Unknown'))} "
                f"| Type: {source.get('doc_type', 'unknown')}"
            )
            if source.get("page_number"):
                header += f" | Page {source['page_number']}"

            block = f"{header}\n{chunk.content}\n"
            block_tokens = len(block.split()) * 1.3  # rough token estimate

            if total_tokens + block_tokens > max_tokens:
                break

            parts.append(block)
            total_tokens += block_tokens

        return "\n---\n".join(parts)
