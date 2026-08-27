"""Vision Worker — Qwen2-VL inference for enterprise image understanding."""
from __future__ import annotations
import asyncio
import base64
import logging
from pathlib import Path
from app.core.config import settings
from workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class VisionWorker(BaseWorker):
    stream_name = settings.STREAM_VISION
    group_name = "vision-group"
    consumer_prefix = "vision-worker"
    batch_size = 1  # GPU memory: one image at a time

    async def setup(self) -> None:
        from workers.vision_worker.qwen_vl import QwenVL
        self._model = QwenVL()
        await self._model.load()
        logger.info("Vision worker ready")

    async def process_message(self, msg_id: str, fields: dict) -> None:
        image_path = fields.get("image_path")
        document_id = fields.get("document_id")
        response_key = fields.get("response_key")  # Redis key to write result to

        if not image_path or not Path(image_path).exists():
            logger.warning(f"Image not found: {image_path}")
            return

        from workers.vision_worker.image_analyzer import ImageAnalyzer
        analyzer = ImageAnalyzer(self._model)
        result = await analyzer.analyze(image_path)

        # Write result to Redis for document processor to pick up
        if response_key:
            import json
            from app.db.redis import set_cache
            await set_cache(response_key, json.dumps(result), ttl=300)

        # Store image features in Qdrant
        if document_id and result.get("visual_embedding"):
            await self._store_image_features(document_id, image_path, result)

        logger.info(f"Vision analysis complete: {image_path} → {result.get('diagram_type')}")

    async def _store_image_features(self, document_id: str, image_path: str, result: dict) -> None:
        try:
            from qdrant_client import models
            from app.db.qdrant import get_qdrant_client
            import uuid

            client = get_qdrant_client()
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"img:{image_path}"))

            visual_vec = result.get("visual_embedding", [0.0] * 512)
            text_vec = result.get("text_embedding", [0.0] * settings.EMBEDDING_DIM)

            await client.upsert(
                collection_name=settings.QDRANT_COLLECTION_IMAGES,
                points=[models.PointStruct(
                    id=point_id,
                    vector={"visual": visual_vec, "text": text_vec},
                    payload={
                        "document_id": document_id,
                        "image_path": image_path,
                        "filename": Path(image_path).name,
                        "diagram_type": result.get("diagram_type", "unknown"),
                        "description": result.get("description", ""),
                        "entities": result.get("entities", []),
                    },
                )],
            )
        except Exception as e:
            logger.error(f"Image feature storage failed: {e}")


if __name__ == "__main__":
    asyncio.run(VisionWorker().run())
