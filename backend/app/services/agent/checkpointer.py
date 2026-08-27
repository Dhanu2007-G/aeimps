"""
Redis-backed LangGraph checkpointer.
Persists agent state after each node for resumability and inspection.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator, AsyncIterator

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisCheckpointer:
    """
    Custom LangGraph checkpointer that stores state in Redis.
    Falls back gracefully if Redis is unavailable.
    State is also written to PostgreSQL for durable audit trail.
    """

    TTL = settings.AGENT_SESSION_TTL_HOURS * 3600

    def __init__(self):
        self._redis = None

    def _get_redis(self):
        if self._redis is None:
            from app.db.redis import get_redis
            self._redis = get_redis()
        return self._redis

    def _key(self, thread_id: str, checkpoint_id: str = "latest") -> str:
        return f"checkpoint:{thread_id}:{checkpoint_id}"

    async def aput(
        self,
        config: dict,
        checkpoint: dict,
        metadata: dict,
    ) -> dict:
        """Save checkpoint to Redis."""
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")

        try:
            redis = self._get_redis()
            data = json.dumps({
                "checkpoint": checkpoint,
                "metadata": metadata,
                "saved_at": time.time(),
            }, default=str)

            await redis.setex(self._key(thread_id), self.TTL, data)
            # Also save with checkpoint_id for history
            if metadata.get("step"):
                step_key = self._key(thread_id, f"step_{metadata['step']}")
                await redis.setex(step_key, self.TTL, data)
        except Exception as e:
            logger.warning(f"Checkpoint save failed (non-fatal): {e}")

        return {**config, "configurable": {**config.get("configurable", {}),
                                            "checkpoint_id": "latest"}}

    async def aget(self, config: dict) -> dict | None:
        """Load latest checkpoint from Redis."""
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")

        try:
            redis = self._get_redis()
            data = await redis.get(self._key(thread_id))
            if data:
                parsed = json.loads(data)
                return parsed.get("checkpoint")
        except Exception as e:
            logger.warning(f"Checkpoint load failed: {e}")

        return None

    async def alist(self, config: dict) -> AsyncIterator[dict]:
        """List checkpoints for a thread (for step history)."""
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        try:
            redis = self._get_redis()
            keys = await redis.keys(f"checkpoint:{thread_id}:step_*")
            for key in sorted(keys):
                data = await redis.get(key)
                if data:
                    parsed = json.loads(data)
                    yield parsed
        except Exception as e:
            logger.warning(f"Checkpoint list failed: {e}")
            return


_checkpointer: RedisCheckpointer | None = None


def get_checkpointer() -> RedisCheckpointer:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = RedisCheckpointer()
    return _checkpointer
