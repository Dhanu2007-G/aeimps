"""
Redis async client wrapper.
Provides connection pooling, Streams helpers, and caching utilities.
"""
from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis


async def check_connection() -> bool:
    try:
        redis = get_redis()
        await redis.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        return False


# ─── Redis Streams ───────────────────────────────────────────

async def publish_to_stream(
    stream: str,
    payload: dict[str, Any],
    max_len: int | None = None,
) -> str:
    """Publish a message to a Redis Stream."""
    redis = get_redis()
    # Convert all values to strings (Redis requirement)
    str_payload = {k: str(v) for k, v in payload.items()}
    msg_id = await redis.xadd(
        stream,
        str_payload,
        maxlen=max_len or settings.REDIS_STREAM_MAX_LEN,
        approximate=True,
    )
    return msg_id


async def ensure_consumer_group(stream: str, group: str) -> None:
    """Create consumer group if it doesn't exist."""
    redis = get_redis()
    try:
        await redis.xgroup_create(stream, group, id="0", mkstream=True)
        logger.info(f"Created consumer group: {group} on {stream}")
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            logger.warning(f"Consumer group creation: {e}")


async def read_from_stream(
    stream: str,
    group: str,
    consumer: str,
    count: int = 10,
    block_ms: int = 5000,
) -> list[tuple[str, dict[str, str]]]:
    """
    Read messages from a Redis Stream consumer group.
    Returns list of (message_id, fields) tuples.
    """
    redis = get_redis()
    try:
        response = await redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=count,
            block=block_ms,
        )
        if not response:
            return []
        messages = []
        for _, msgs in response:
            for msg_id, fields in msgs:
                messages.append((msg_id, fields))
        return messages
    except Exception as e:
        logger.error(f"Stream read error: {e}")
        return []


async def ack_stream_message(stream: str, group: str, msg_id: str) -> None:
    """Acknowledge a processed stream message."""
    redis = get_redis()
    await redis.xack(stream, group, msg_id)


async def nack_to_dlq(
    stream: str,
    group: str,
    msg_id: str,
    fields: dict,
    error: str,
) -> None:
    """Move failed message to dead letter queue."""
    redis = get_redis()
    dlq_payload = {**fields, "error": error, "original_stream": stream}
    await publish_to_stream(settings.STREAM_DLQ, dlq_payload)
    await redis.xack(stream, group, msg_id)
    logger.warning(f"Message {msg_id} moved to DLQ: {error}")


async def set_worker_heartbeat(worker_id: str) -> None:
    """Update worker heartbeat timestamp."""
    redis = get_redis()
    import time
    await redis.hset("workers:heartbeat", worker_id, str(time.time()))
    await redis.expire("workers:heartbeat", 300)


async def get_worker_heartbeats() -> dict[str, float]:
    """Get all worker heartbeat timestamps."""
    redis = get_redis()
    raw = await redis.hgetall("workers:heartbeat")
    return {k: float(v) for k, v in raw.items()}


async def set_cache(key: str, value: str, ttl: int = 3600) -> None:
    redis = get_redis()
    await redis.setex(key, ttl, value)


async def get_cache(key: str) -> str | None:
    redis = get_redis()
    return await redis.get(key)


async def delete_cache(key: str) -> None:
    redis = get_redis()
    await redis.delete(key)


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        logger.info("Redis connection closed")
