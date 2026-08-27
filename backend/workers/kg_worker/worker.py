"""Knowledge Graph Worker — NER, relation extraction, Neo4j population."""
from __future__ import annotations
import asyncio
import logging
from app.core.config import settings
from workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class KGWorker(BaseWorker):
    stream_name = settings.STREAM_KG
    group_name = "kg-group"
    consumer_prefix = "kg-worker"
    batch_size = 5

    async def setup(self) -> None:
        from workers.kg_worker.ner_pipeline import NERPipeline
        self._ner = NERPipeline()
        await self._ner.setup()
        logger.info("KG worker ready")

    async def process_message(self, msg_id: str, fields: dict) -> None:
        document_id = fields.get("document_id")
        if not document_id:
            return

        # Load all text chunks for this document
        chunks = await self._load_chunks(document_id)
        if not chunks:
            return

        logger.info(f"KG processing {len(chunks)} chunks for {document_id}")

        from workers.kg_worker.ner_pipeline import NERPipeline
        from workers.kg_worker.entity_resolver import EntityResolver
        from workers.kg_worker.neo4j_writer import Neo4jWriter

        ner = NERPipeline()
        resolver = EntityResolver()
        writer = Neo4jWriter()

        # NER over all chunks
        all_entities: list[dict] = []
        for chunk in chunks:
            entities = await ner.extract(chunk["content"], chunk["id"])
            all_entities.extend(entities)

        # Entity resolution (dedup + merge)
        resolved = await resolver.resolve(all_entities)

        # Write to Neo4j
        await writer.write_document(document_id, resolved)

        # Mark chunks as KG-processed
        await self._mark_kg_processed([c["id"] for c in chunks])
        logger.info(f"KG: wrote {len(resolved)} entities for document {document_id}")

    async def _load_chunks(self, document_id: str) -> list[dict]:
        from sqlalchemy import select
        from app.db.postgres import get_db
        from app.db.models import DocumentChunk

        async with get_db() as db:
            result = await db.execute(
                select(DocumentChunk.id, DocumentChunk.content, DocumentChunk.chunk_type)
                .where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.chunk_type.in_(["text", "section_header"]),
                    DocumentChunk.is_kg_processed == False,
                )
                .limit(200)
            )
            return [{"id": str(r.id), "content": r.content, "chunk_type": r.chunk_type}
                    for r in result.fetchall()]

    async def _mark_kg_processed(self, chunk_ids: list[str]) -> None:
        from sqlalchemy import update
        from app.db.postgres import get_db
        from app.db.models import DocumentChunk

        async with get_db() as db:
            await db.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id.in_(chunk_ids))
                .values(is_kg_processed=True)
            )


if __name__ == "__main__":
    asyncio.run(KGWorker().run())
