"""
Base Redis Streams Worker
All AEIMPS workers inherit from this. Provides:
- Consumer group management
- Claim-process-ACK pattern
- Heartbeat emission
- Dead letter queue routing
- Graceful shutdown
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
import traceback
from abc import ABC, abstractmethod

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.redis import (
    ack_stream_message,
    ensure_consumer_group,
    nack_to_dlq,
    read_from_stream,
    set_worker_heartbeat,
)

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """
    Base class for all Redis Streams workers.
    Subclasses implement process_message() only.
    """

    stream_name: str = ""
    group_name: str = ""
    consumer_prefix: str = "worker"
    batch_size: int = 5
    heartbeat_interval: int = 30

    def __init__(self):
        self.worker_id = f"{self.consumer_prefix}_{os.getpid()}"
        self._running = False
        self._last_heartbeat = 0.0

    @abstractmethod
    async def process_message(self, msg_id: str, fields: dict) -> None:
        """Process a single message from the stream. Must be implemented by subclass."""

    async def setup(self) -> None:
        """Called once before the main loop. Override for model loading etc."""

    async def teardown(self) -> None:
        """Called on shutdown."""

    async def run(self) -> None:
        """Main worker loop."""
        setup_logging(settings.LOG_LEVEL)
        logger.info(f"Worker starting: {self.worker_id} → {self.stream_name}")

        # Graceful shutdown hooks
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown)

        try:
            await self.setup()
            await ensure_consumer_group(self.stream_name, self.group_name)
            self._running = True

            # Reclaim pending messages from dead workers first
            await self._reclaim_pending()

            while self._running:
                await self._heartbeat()

                messages = await read_from_stream(
                    self.stream_name,
                    self.group_name,
                    self.worker_id,
                    count=self.batch_size,
                    block_ms=settings.REDIS_WORKER_BLOCK_MS,
                )

                for msg_id, fields in messages:
                    if not self._running:
                        break
                    await self._handle_message(msg_id, fields)

        except Exception as e:
            logger.error(f"Worker {self.worker_id} fatal error: {e}", exc_info=True)
        finally:
            await self.teardown()
            logger.info(f"Worker {self.worker_id} stopped")

    async def _handle_message(self, msg_id: str, fields: dict) -> None:
        attempts = int(fields.get("_attempts", "0"))
        start = time.monotonic()

        try:
            logger.debug(f"Processing message {msg_id}")
            await self.process_message(msg_id, fields)
            await ack_stream_message(self.stream_name, self.group_name, msg_id)
            duration = int((time.monotonic() - start) * 1000)
            logger.info(f"Message {msg_id} processed in {duration}ms")

        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            logger.error(f"Message {msg_id} failed (attempt {attempts+1}): {e}")

            if attempts >= 2:
                logger.warning(f"Message {msg_id} exceeded max attempts → DLQ")
                await nack_to_dlq(
                    self.stream_name, self.group_name, msg_id,
                    {**fields, "_attempts": str(attempts + 1)},
                    error=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()[-500:]}",
                )
            else:
                # Re-publish with incremented attempt counter
                from app.db.redis import publish_to_stream
                await publish_to_stream(
                    self.stream_name,
                    {**fields, "_attempts": str(attempts + 1)},
                )
                await ack_stream_message(self.stream_name, self.group_name, msg_id)

    async def _heartbeat(self) -> None:
        now = time.time()
        if now - self._last_heartbeat > self.heartbeat_interval:
            await set_worker_heartbeat(self.worker_id)
            self._last_heartbeat = now

    async def _reclaim_pending(self) -> None:
        """Reclaim messages from workers that haven't acknowledged in >5min."""
        try:
            from app.db.redis import get_redis
            redis = get_redis()
            # XAUTOCLAIM: reclaim messages pending > 5 minutes
            result = await redis.xautoclaim(
                self.stream_name,
                self.group_name,
                self.worker_id,
                min_idle_time=300000,  # 5 minutes in ms
                start_id="0-0",
                count=50,
            )
            if result and result[1]:
                logger.info(f"Reclaimed {len(result[1])} pending messages")
        except Exception as e:
            logger.debug(f"Reclaim failed (non-fatal): {e}")

    def _handle_shutdown(self) -> None:
        logger.info(f"Shutdown signal received for {self.worker_id}")
        self._running = False
