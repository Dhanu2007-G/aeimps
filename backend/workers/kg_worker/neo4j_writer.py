"""Neo4j Writer — batch MERGE operations for entities and relationships."""
from __future__ import annotations
import logging
import uuid
from app.db.neo4j import run_query

logger = logging.getLogger(__name__)


class Neo4jWriter:
    async def write_document(self, document_id: str, entities: list[dict]) -> None:
        # Ensure document node exists
        await run_query("""
            MERGE (d:Document {id: $doc_id})
            ON CREATE SET d.created_at = datetime()
        """, {"doc_id": document_id})

        # Write entities in batches
        batch_size = 50
        for i in range(0, len(entities), batch_size):
            batch = entities[i:i + batch_size]
            await self._write_entity_batch(document_id, batch)

    async def _write_entity_batch(self, document_id: str, batch: list[dict]) -> None:
        for ent in batch:
            entity_id = str(uuid.uuid5(uuid.NAMESPACE_DNS,
                                        ent.get("canonical_name", ent["name"])))
            try:
                await run_query("""
                    MERGE (e:Entity {id: $id})
                    ON CREATE SET
                        e.name = $name,
                        e.canonical_name = $canonical,
                        e.type = $type,
                        e.created_at = datetime()
                    ON MATCH SET
                        e.updated_at = datetime()
                    WITH e
                    MATCH (d:Document {id: $doc_id})
                    MERGE (e)-[:MENTIONED_IN {confidence: $confidence}]->(d)
                    MERGE (d)-[:CONTAINS]->(e)
                """, {
                    "id": entity_id,
                    "name": ent["name"],
                    "canonical": ent.get("canonical_name", ent["name"]),
                    "type": ent.get("type", "CONCEPT"),
                    "doc_id": document_id,
                    "confidence": ent.get("confidence", 0.7),
                })

                # Sync to PostgreSQL kg_entities table
                await self._sync_pg_entity(entity_id, ent)

            except Exception as e:
                logger.warning(f"Entity write failed for {ent['name']}: {e}")

    async def _sync_pg_entity(self, neo4j_id: str, ent: dict) -> None:
        try:
            from sqlalchemy.dialects.postgresql import insert
            from app.db.postgres import get_db
            from app.db.models import KGEntity

            async with get_db() as db:
                stmt = insert(KGEntity).values(
                    neo4j_id=neo4j_id,
                    entity_type=ent.get("type", "CONCEPT"),
                    canonical_name=ent.get("canonical_name", ent["name"])[:500],
                    aliases=list(set([ent["name"]])),
                ).on_conflict_do_update(
                    index_elements=["neo4j_id"],
                    set_={"document_count": KGEntity.document_count + 1},
                )
                await db.execute(stmt)
        except Exception as e:
            logger.debug(f"PG entity sync failed (non-critical): {e}")
