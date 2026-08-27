"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"pg_trgm\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"btree_gin\"")

    # ─── api_keys ─────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("key_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("permissions", postgresql.ARRAY(sa.String), nullable=False,
                  server_default=sa.text("ARRAY['read','write']::varchar[]")),
        sa.Column("rate_limit_rpm", sa.Integer, nullable=False, default=60),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─── documents ────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("original_name", sa.String(500), nullable=False),
        sa.Column("doc_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column("file_hash", sa.String(64), unique=True),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("page_count", sa.Integer),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("tags", postgresql.ARRAY(sa.String)),
        sa.Column("source_system", sa.String(100)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_documents_status", "documents", ["status"])
    op.create_index("idx_documents_doc_type", "documents", ["doc_type"])
    op.create_index("idx_documents_created_at", "documents", ["created_at"])
    op.execute("""
        CREATE INDEX idx_documents_tags ON documents USING GIN(tags)
        WHERE tags IS NOT NULL
    """)
    op.execute("CREATE INDEX idx_documents_metadata ON documents USING GIN(metadata)")

    # ─── document_chunks ──────────────────────────────────────
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_type", sa.String(30), nullable=False, server_default="text"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer),
        sa.Column("page_number", sa.Integer),
        sa.Column("bounding_box", postgresql.JSONB),
        sa.Column("table_data", postgresql.JSONB),
        sa.Column("code_language", sa.String(50)),
        sa.Column("embedding_id", sa.String(100)),
        sa.Column("embedding_model", sa.String(100)),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_embedded", sa.Boolean, nullable=False, server_default="FALSE"),
        sa.Column("is_kg_processed", sa.Boolean, nullable=False, server_default="FALSE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Full-text search vector
    op.execute("""
        ALTER TABLE document_chunks
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
    """)
    op.create_index("idx_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("idx_chunks_type", "document_chunks", ["chunk_type"])
    op.execute(
        "CREATE INDEX idx_chunks_content_tsv ON document_chunks USING GIN(content_tsv)"
    )
    op.execute("""
        CREATE INDEX idx_chunks_not_embedded ON document_chunks(document_id)
        WHERE is_embedded = FALSE
    """)

    # ─── processing_jobs ──────────────────────────────────────
    op.create_table(
        "processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("priority", sa.SmallInteger, nullable=False, server_default="5"),
        sa.Column("worker_id", sa.String(100)),
        sa.Column("attempts", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.SmallInteger, nullable=False, server_default="3"),
        sa.Column("input_payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("output_payload", postgresql.JSONB),
        sa.Column("error_message", sa.Text),
        sa.Column("error_trace", sa.Text),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_jobs_status", "processing_jobs", ["status", "priority"])
    op.create_index("idx_jobs_document_id", "processing_jobs", ["document_id"])

    # ─── agent_sessions ───────────────────────────────────────
    op.create_table(
        "agent_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", sa.String(100), unique=True, nullable=False),
        sa.Column("workflow_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="INITIALIZING"),
        sa.Column("input_query", sa.Text, nullable=False),
        sa.Column("input_context", postgresql.JSONB),
        sa.Column("final_response", sa.Text),
        sa.Column("response_metadata", postgresql.JSONB),
        sa.Column("confidence_score", sa.Float),
        sa.Column("total_duration_ms", sa.Integer),
        sa.Column("total_tokens_used", sa.Integer),
        sa.Column("llm_model", sa.String(100)),
        sa.Column("error_message", sa.Text),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("api_keys.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_sessions_status", "agent_sessions", ["status"])
    op.create_index("idx_sessions_workflow", "agent_sessions", ["workflow_type"])
    op.create_index("idx_sessions_created_at", "agent_sessions", ["created_at"])

    # ─── agent_steps ──────────────────────────────────────────
    op.create_table(
        "agent_steps",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_index", sa.SmallInteger, nullable=False),
        sa.Column("node_name", sa.String(100), nullable=False),
        sa.Column("input_state", postgresql.JSONB),
        sa.Column("output_state", postgresql.JSONB),
        sa.Column("tool_calls", postgresql.JSONB),
        sa.Column("tool_results", postgresql.JSONB),
        sa.Column("llm_prompt", sa.Text),
        sa.Column("llm_response", sa.Text),
        sa.Column("tokens_used", sa.Integer),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_steps_session_id", "agent_steps", ["session_id"])

    # ─── retrieval_logs ───────────────────────────────────────
    op.create_table(
        "retrieval_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("agent_sessions.id", ondelete="SET NULL")),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("retrieval_mode", sa.String(50), nullable=False),
        sa.Column("num_candidates", sa.Integer),
        sa.Column("num_returned", sa.Integer),
        sa.Column("top_chunk_ids", postgresql.JSONB),
        sa.Column("scores", postgresql.JSONB),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("filter_applied", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ─── evaluations ──────────────────────────────────────────
    op.create_table(
        "evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("agent_sessions.id", ondelete="SET NULL")),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("response", sa.Text, nullable=False),
        sa.Column("retrieved_context", postgresql.JSONB),
        sa.Column("reference_answer", sa.Text),
        sa.Column("faithfulness", sa.Float),
        sa.Column("context_recall", sa.Float),
        sa.Column("context_precision", sa.Float),
        sa.Column("answer_relevance", sa.Float),
        sa.Column("hallucination_score", sa.Float),
        sa.Column("overall_score", sa.Float),
        sa.Column("eval_model", sa.String(100)),
        sa.Column("eval_metadata", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_eval_session", "evaluations", ["session_id"])
    op.create_index("idx_eval_score", "evaluations", ["overall_score"])

    # ─── kg_entities ──────────────────────────────────────────
    op.create_table(
        "kg_entities",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("neo4j_id", sa.String(200), unique=True, nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("canonical_name", sa.String(500), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.String)),
        sa.Column("embedding_id", sa.String(100)),
        sa.Column("document_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_kg_entities_type", "kg_entities", ["entity_type"])


def downgrade() -> None:
    for table in [
        "kg_entities", "evaluations", "retrieval_logs",
        "agent_steps", "agent_sessions", "processing_jobs",
        "document_chunks", "documents", "api_keys",
    ]:
        op.drop_table(table)
