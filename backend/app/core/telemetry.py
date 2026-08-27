"""
OpenTelemetry instrumentation for distributed tracing.
Exports to OTLP collector → Jaeger or any compatible backend.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

logger = logging.getLogger(__name__)


def setup_telemetry(
    service_name: str,
    otlp_endpoint: str,
    environment: str = "production",
    sample_rate: float = 1.0,
) -> TracerProvider:
    """Initialize OpenTelemetry with OTLP export."""
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
        "deployment.environment": environment,
    })

    sampler = ParentBasedTraceIdRatio(sample_rate)
    provider = TracerProvider(resource=resource, sampler=sampler)

    # OTLP gRPC exporter (primary)
    try:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info("OTLP exporter configured", extra={"endpoint": otlp_endpoint})
    except Exception as e:
        logger.warning(f"OTLP exporter failed, using console: {e}")
        if environment == "development":
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    # Auto-instrument SQLAlchemy
    SQLAlchemyInstrumentor().instrument(enable_commenter=True)

    return provider


def instrument_fastapi(app) -> None:
    """Auto-instrument FastAPI application."""
    FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str = "aeimps") -> trace.Tracer:
    return trace.get_tracer(name)


@contextmanager
def trace_span(
    name: str,
    attributes: dict | None = None,
) -> Generator[trace.Span, None, None]:
    """Context manager for manual span creation."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        yield span
