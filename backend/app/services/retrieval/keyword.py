"""PostgreSQL full-text search keyword retrieval using tsvector."""
from __future__ import annotations
import logging
from app.services.retrieval.orchestrator import ChunkResult

logger = logging.getLogger(__name__)


class KeywordRetriever:
    async def search(self, query: str, top_k: int, filters: dict) -> list[ChunkResult]:
        from sqlalchemy import text
        from app.db.postgres import get_db

        # Build plainto_tsquery for robust FTS
        fts_query = " & ".join(query.split()[:20])  # Max 20 terms

        sql_parts = ["""
            SELECT
                c.id,
                c.document_id,
                c.content,
                c.chunk_type,
                c.metadata,
                c.page_number,
                d.filename,
                d.original_name,
                d.doc_type,
                ts_rank_cd(c.content_tsv, plainto_tsquery('english', :query), 32) AS score
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE
                c.content_tsv @@ plainto_tsquery('english', :query)
                AND c.is_embedded = TRUE
        """]

        params: dict = {"query": query, "limit": top_k}

        if filters.get("doc_types"):
            sql_parts.append("AND d.doc_type = ANY(:doc_types)")
            params["doc_types"] = filters["doc_types"]

        if filters.get("date_from"):
            sql_parts.append("AND d.created_at >= :date_from")
            params["date_from"] = filters["date_from"]

        if filters.get("date_to"):
            sql_parts.append("AND d.created_at <= :date_to")
            params["date_to"] = filters["date_to"]

        sql_parts.append("ORDER BY score DESC LIMIT :limit")
        sql = " ".join(sql_parts)

        try:
            async with get_db() as db:
                result = await db.execute(text(sql), params)
                rows = result.fetchall()

            return [
                ChunkResult(
                    chunk_id=str(row.id),
                    document_id=str(row.document_id),
                    content=row.content,
                    chunk_type=row.chunk_type,
                    score=float(row.score),
                    source_doc={
                        "filename": row.filename,
                        "original_name": row.original_name,
                        "doc_type": row.doc_type,
                        "page_number": row.page_number,
                    },
                    metadata=row.metadata or {},
                )
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []
