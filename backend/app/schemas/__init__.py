"""
AEIMPS API Schemas - Complete request/response models.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ─── Common ──────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    error: ErrorDetail


class PaginationMeta(BaseModel):
    total: int | None = None
    next_cursor: str | None = None
    limit: int


# ─── Ingest ──────────────────────────────────────────────────

class IngestResponse(BaseModel):
    job_id: str
    document_id: str
    status: str
    filename: str
    file_size_bytes: int | None = None
    estimated_duration_seconds: int = 60
    message: str = "Document queued for processing"


class BatchIngestResponse(BaseModel):
    batch_id: str
    jobs: list[IngestResponse]
    total: int


class JobStatusResponse(BaseModel):
    job_id: str
    document_id: str | None
    job_type: str
    status: str
    progress_pct: int = 0
    worker_id: str | None = None
    attempts: int = 0
    error: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None


class DocumentResponse(BaseModel):
    id: str
    filename: str
    original_name: str
    doc_type: str
    status: str
    file_size_bytes: int | None = None
    page_count: int | None = None
    tags: list[str] | None = None
    source_system: str | None = None
    metadata: dict[str, Any] = {}
    chunks_count: int = 0
    embedding_coverage_pct: float = 0.0
    kg_entities_count: int = 0
    created_at: datetime
    processed_at: datetime | None = None


class JobListResponse(BaseModel):
    jobs: list[JobStatusResponse]
    next_cursor: str | None = None
    total: int | None = None


# ─── Retrieve ────────────────────────────────────────────────

class SearchFilters(BaseModel):
    doc_types: list[str] | None = None
    tags: list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    source_systems: list[str] | None = None
    chunk_types: list[str] | None = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    mode: Literal["hybrid", "dense", "sparse", "keyword", "graph"] = "hybrid"
    filters: SearchFilters = Field(default_factory=SearchFilters)
    top_k: int = Field(default=8, ge=1, le=20)
    include_metadata: bool = True
    include_parent_context: bool = True


class ChunkSource(BaseModel):
    document_id: str
    filename: str
    original_name: str
    doc_type: str
    page_number: int | None = None


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    chunk_type: str
    score: float
    rank: int
    source: ChunkSource
    metadata: dict[str, Any] = {}
    highlights: list[str] = []


class QueryMetadata(BaseModel):
    entities_detected: list[str] = []
    sub_queries: list[str] = []
    retrieval_latency_ms: int = 0
    mode_scores: dict[str, float] = {}
    reranker_applied: bool = False
    total_candidates: int = 0


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total_results: int
    query_metadata: QueryMetadata


class MultimodalSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    image_base64: str | None = None
    top_k: int = Field(default=8, ge=1, le=20)


class EntityResponse(BaseModel):
    entity: dict[str, Any]
    related_entities: list[dict[str, Any]] = []
    source_documents: list[str] = []
    graph_neighborhood: dict[str, Any] = {}


# ─── Agent ───────────────────────────────────────────────────

class AgentContextConfig(BaseModel):
    document_ids: list[str] = []
    time_window: dict[str, str] | None = None
    entities: list[str] = []


class AgentRunConfig(BaseModel):
    max_iterations: int = Field(default=8, ge=1, le=20)
    min_confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    include_evaluation: bool = True
    timeout_seconds: int = Field(default=300, ge=30, le=600)


class AgentRunRequest(BaseModel):
    workflow: Literal[
        "incident_investigation",
        "question_answering",
        "summarization",
        "root_cause_analysis",
        "remediation",
    ]
    input: str = Field(..., min_length=1, max_length=10000)
    context: AgentContextConfig = Field(default_factory=AgentContextConfig)
    config: AgentRunConfig = Field(default_factory=AgentRunConfig)


class AgentRunResponse(BaseModel):
    session_id: str
    status: str = "RUNNING"
    workflow: str
    estimated_duration_seconds: int = 30
    message: str = "Agent workflow started"


class AgentStepSummary(BaseModel):
    node: str
    step_index: int
    summary: str
    tool_calls_count: int = 0
    duration_ms: int | None = None
    created_at: datetime


class CitationSource(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    content_preview: str
    relevance_score: float


class AgentResult(BaseModel):
    response: str
    confidence: float
    sources: list[CitationSource] = []
    graph_entities_used: list[str] = []
    total_tokens: int = 0


class EvaluationScores(BaseModel):
    faithfulness: float | None = None
    context_recall: float | None = None
    context_precision: float | None = None
    answer_relevance: float | None = None
    hallucination_score: float | None = None
    overall_score: float | None = None


class AgentSessionResponse(BaseModel):
    session_id: str
    workflow: str
    status: str
    current_node: str | None = None
    input_query: str
    steps: list[AgentStepSummary] = []
    result: AgentResult | None = None
    evaluation: EvaluationScores | None = None
    total_duration_ms: int | None = None
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class AgentContinueRequest(BaseModel):
    input: str = Field(..., min_length=1)


class AgentListResponse(BaseModel):
    sessions: list[AgentSessionResponse]
    next_cursor: str | None = None


# ─── Evaluate ────────────────────────────────────────────────

class EvaluationTriggerResponse(BaseModel):
    evaluation_id: str
    session_id: str
    status: str = "RUNNING"


class EvaluationResultResponse(BaseModel):
    evaluation_id: str
    session_id: str | None
    query: str
    response_preview: str
    scores: EvaluationScores
    details: dict[str, Any] = {}
    eval_model: str | None = None
    created_at: datetime


class EvaluationSummaryResponse(BaseModel):
    period: dict[str, str]
    total_evaluations: int
    average_scores: EvaluationScores
    score_distribution: dict[str, int]
    worst_performing: list[dict[str, Any]] = []
    trend: list[dict[str, Any]] = []


class BatchEvaluationRequest(BaseModel):
    session_ids: list[str] = Field(..., min_length=1, max_length=100)


class BatchEvaluationResponse(BaseModel):
    batch_id: str
    evaluations_queued: int


# ─── Admin ───────────────────────────────────────────────────

class ServiceHealthStatus(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    latency_ms: int | None = None
    details: str | None = None


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    environment: str
    uptime_seconds: float
    services: dict[str, ServiceHealthStatus]
    timestamp: datetime


class SystemMetricsSummary(BaseModel):
    documents_total: int
    chunks_total: int
    vectors_total: int
    agents_run_today: int
    avg_retrieval_ms: float | None
    eval_avg_score: float | None


class WorkerStatus(BaseModel):
    name: str
    status: Literal["alive", "stale", "dead"]
    last_heartbeat: float | None
    seconds_since_heartbeat: float | None
