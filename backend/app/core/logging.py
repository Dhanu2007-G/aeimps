"""
Structured JSON logging for production observability.
Integrates with OpenTelemetry trace context injection.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import orjson


class StructuredFormatter(logging.Formatter):
    """JSON log formatter for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Inject trace context if available
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            if span.is_recording():
                ctx = span.get_span_context()
                log_data["trace_id"] = format(ctx.trace_id, "032x")
                log_data["span_id"] = format(ctx.span_id, "016x")
        except Exception:
            pass

        # Include extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Include exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        try:
            return orjson.dumps(log_data).decode()
        except Exception:
            return str(log_data)


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging for the application."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in [
        "uvicorn.access", "httpx", "httpcore",
        "opentelemetry", "asyncio", "neo4j.notifications",
    ]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
