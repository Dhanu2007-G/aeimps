"""Knowledge graph traversal retrieval via Neo4j Cypher queries."""
from __future__ import annotations
import logging
from app.services.retrieval.orchestrator import ChunkResult

logger = logging.getLogger(__name__)


class GraphRetriever:
    async def search(
        self,
        entities: list[str],
        top_k: int,
        filters: dict,
    ) -> list[ChunkResult]:
        """
        Find relevant chunks by traversing the entity knowledge graph.
        Seeds from query entities, traverses up to 2 hops.
        """
        if not entities:
            return []

        from app.db.neo4j import run_query
        from app.db.postgres import get_db
        from sqlalchemy import text

        # Find documents containing the query entities and related entities
        cypher = """
        CALL db.index.fulltext.queryNodes('entity_search', $search_text)
        YIELD node AS e, score
        WITH e, score
        LIMIT 10
        MATCH (e)-[:MENTIONED_IN]->(d:Document)
        WITH d, max(score) AS rel_score
        OPTIONAL MATCH (d)-[:CONTAINS]->(e2:Entity)
        RETURN DISTINCT d.id AS document_id, rel_score,
               collect(DISTINCT e2.name)[..5] AS entities
        ORDER BY rel_score DESC
        LIMIT $limit
        """
        search_text = " OR ".join(entities[:5])

        try:
            graph_results = await run_query(cypher, {
                "search_text": search_text,
                "limit": top_k * 2,
            })
        except Exception as e:
            logger.error(f"Neo4j query failed: {e}")
            return []

        if not graph_results:
            return []

        doc_ids = [r["document_id"] for r in graph_results if r.get("document_id")]
        if not doc_ids:
            return []

        # Fetch actual chunks from PostgreSQL for those documents
        try:
            async with get_db() as db:
                result = await db.execute(
                    text("""
                        SELECT
                            c.id, c.document_id, c.content, c.chunk_type,
                            c.metadata, c.page_number,
                            d.filename, d.original_name, d.doc_type
                        FROM document_chunks c
                        JOIN documents d ON d.id = c.document_id
                        WHERE c.document_id = ANY(:doc_ids)
                          AND c.is_embedded = TRUE
                          AND c.chunk_type IN ('text', 'section_header')
                        ORDER BY c.chunk_index
                        LIMIT :limit
                    """),
                    {"doc_ids": doc_ids, "limit": top_k},
                )
                rows = result.fetchall()
        except Exception as e:
            logger.error(f"PostgreSQL graph chunk fetch failed: {e}")
            return []

        # Score based on graph relevance (doc position in graph results)
        doc_scores = {r["document_id"]: r["rel_score"] for r in graph_results}

        return [
            ChunkResult(
                chunk_id=str(row.id),
                document_id=str(row.document_id),
                content=row.content,
                chunk_type=row.chunk_type,
                score=float(doc_scores.get(str(row.document_id), 0.5)),
                source_doc={
                    "filename": row.filename,
                    "original_name": row.original_name,
                    "doc_type": row.doc_type,
                    "page_number": row.page_number,
                },
                metadata=row.metadata or {},
                retrieval_mode="graph",
            )
            for row in rows
        ]
