"""SQLAlchemy ORM models for AEIMPS."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ─── Documents ───────────────────────────────────────────────

class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING", index=True
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    file_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    page_count: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    source_system: Mapped[str | None] = mapped_column(String(100))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["ProcessingJob"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_documents_status", "status"),
        Index("idx_documents_doc_type", "doc_type"),
        Index("idx_documents_created_at", "created_at"),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(30), nullable=False, default="text")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    bounding_box: Mapped[dict | None] = mapped_column(JSONB)
    table_data: Mapped[dict | None] = mapped_column(JSONB)
    code_language: Mapped[str | None] = mapped_column(String(50))
    embedding_id: Mapped[str | None] = mapped_column(String(100))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    is_embedded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_kg_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("idx_chunks_document_id", "document_id"),
        Index("idx_chunks_type", "chunk_type"),
        Index("idx_chunks_not_embedded", "document_id",
              postgresql_where="is_embedded = FALSE"),
    )


# ─── Processing Jobs ─────────────────────────────────────────

class ProcessingJob(Base, TimestampMixin):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    document_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="SET NULL")
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING", index=True
    )
    priority: Mapped[int] = mapped_column(SmallInteger, default=5)
    worker_id: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, default=3)
    input_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_payload: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_trace: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped["Document | None"] = relationship(back_populates="jobs")

    __table_args__ = (
        Index("idx_jobs_status", "status", "priority"),
        Index("idx_jobs_document_id", "document_id"),
    )


# ─── Agent Sessions ──────────────────────────────────────────

class AgentSession(Base, TimestampMixin):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    session_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    workflow_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="INITIALIZING", index=True
    )
    input_query: Mapped[str] = mapped_column(Text, nullable=False)
    input_context: Mapped[dict | None] = mapped_column(JSONB)
    final_response: Mapped[str | None] = mapped_column(Text)
    response_metadata: Mapped[dict | None] = mapped_column(JSONB)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    total_duration_ms: Mapped[int | None] = mapped_column(Integer)
    total_tokens_used: Mapped[int | None] = mapped_column(Integer)
    llm_model: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    api_key_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("api_keys.id", ondelete="SET NULL")
    )

    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_sessions_status", "status"),
        Index("idx_sessions_workflow", "workflow_type"),
        Index("idx_sessions_created_at", "created_at"),
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_state: Mapped[dict | None] = mapped_column(JSONB)
    output_state: Mapped[dict | None] = mapped_column(JSONB)
    tool_calls: Mapped[list | None] = mapped_column(JSONB)
    tool_results: Mapped[dict | None] = mapped_column(JSONB)
    llm_prompt: Mapped[str | None] = mapped_column(Text)
    llm_response: Mapped[str | None] = mapped_column(Text)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped["AgentSession"] = relationship(back_populates="steps")

    __table_args__ = (Index("idx_steps_session_id", "session_id"),)


# ─── Retrieval Logs ──────────────────────────────────────────

class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    session_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("agent_sessions.id", ondelete="SET NULL")
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    num_candidates: Mapped[int | None] = mapped_column(Integer)
    num_returned: Mapped[int | None] = mapped_column(Integer)
    top_chunk_ids: Mapped[list | None] = mapped_column(JSONB)
    scores: Mapped[list | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    filter_applied: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ─── Evaluations ─────────────────────────────────────────────

class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    session_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("agent_sessions.id", ondelete="SET NULL")
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_context: Mapped[dict | None] = mapped_column(JSONB)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    faithfulness: Mapped[float | None] = mapped_column(Float)
    context_recall: Mapped[float | None] = mapped_column(Float)
    context_precision: Mapped[float | None] = mapped_column(Float)
    answer_relevance: Mapped[float | None] = mapped_column(Float)
    hallucination_score: Mapped[float | None] = mapped_column(Float)
    overall_score: Mapped[float | None] = mapped_column(Float)
    eval_model: Mapped[str | None] = mapped_column(String(100))
    eval_metadata: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped["AgentSession | None"] = relationship(back_populates="evaluations")

    __table_args__ = (
        Index("idx_eval_session", "session_id"),
        Index("idx_eval_score", "overall_score"),
    )


# ─── KG Cross-Reference ──────────────────────────────────────

class KGEntity(Base, TimestampMixin):
    __tablename__ = "kg_entities"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    neo4j_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    embedding_id: Mapped[str | None] = mapped_column(String(100))
    document_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("idx_kg_entities_type", "entity_type"),)


# ─── Auth ────────────────────────────────────────────────────

class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=lambda: ["read", "write"]
    )
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )



# ─── Users & Roles ───────────────────────────────────────────

import enum


class UserRole(str, enum.Enum):
    """User role hierarchy: ADMIN > MANAGER > ANALYST > VIEWER"""
    ADMIN = "admin"
    MANAGER = "manager"
    ANALYST = "analyst"
    VIEWER = "viewer"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))  # Null for SSO-only users
    role: Mapped[UserRole] = mapped_column(
        String(20), nullable=False, default=UserRole.VIEWER, index=True
    )
    status: Mapped[UserStatus] = mapped_column(
        String(20), nullable=False, default=UserStatus.ACTIVE, index=True
    )
    is_sso_user: Mapped[bool] = mapped_column(Boolean, default=False)
    sso_provider: Mapped[str | None] = mapped_column(String(50))
    sso_subject: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_reset_token: Mapped[str | None] = mapped_column(String(255))
    password_reset_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_users_role", "role"),
        Index("idx_users_status", "status"),
        Index("idx_users_email", "email"),
    )



# ─── Audit Logging ───────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    api_key_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("api_keys.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(100))
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text)
    request_payload: Mapped[dict | None] = mapped_column(JSONB)
    response_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("idx_audit_user_id", "user_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )



# ─── Resource Quotas ─────────────────────────────────────────

class ResourceQuota(Base, TimestampMixin):
    __tablename__ = "resource_quotas"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    max_documents: Mapped[int] = mapped_column(Integer, default=1000)
    max_storage_bytes: Mapped[int] = mapped_column(BigInteger, default=10 * 1024 * 1024 * 1024)  # 10GB
    max_agent_sessions_per_day: Mapped[int] = mapped_column(Integer, default=50)
    current_documents: Mapped[int] = mapped_column(Integer, default=0)
    current_storage_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    current_agent_sessions_today: Mapped[int] = mapped_column(Integer, default=0)
    last_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ─── Data Retention ──────────────────────────────────────────

class RetentionPolicy(Base, TimestampMixin):
    __tablename__ = "retention_policies"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)  # document, audit_log
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    archive_before_delete: Mapped[bool] = mapped_column(Boolean, default=True)
    match_criteria: Mapped[dict] = mapped_column(JSONB, default=dict)  # tags, doc_type, etc.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))



# ─── SAML Configuration ──────────────────────────────────────

class SAMLConfig(Base, TimestampMixin):
    __tablename__ = "saml_configs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # okta, azure_ad, google
    entity_id: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    sso_url: Mapped[str] = mapped_column(String(500), nullable=False)
    slo_url: Mapped[str | None] = mapped_column(String(500))
    x509_cert: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_url: Mapped[str | None] = mapped_column(String(500))
    attribute_mapping: Mapped[dict] = mapped_column(JSONB, default=dict)  # SAML attrs -> user fields
    role_mapping: Mapped[dict] = mapped_column(JSONB, default=dict)  # SAML groups -> roles
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    jit_provisioning: Mapped[bool] = mapped_column(Boolean, default=True)
