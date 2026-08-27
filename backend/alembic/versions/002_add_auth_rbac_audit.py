"""Add user auth, RBAC, audit logging, quotas, retention, and SAML

Revision ID: 002
Revises: 001
Create Date: 2026-06-09 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('is_sso_user', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sso_provider', sa.String(length=50), nullable=True),
        sa.Column('sso_subject', sa.String(length=255), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('password_reset_token', sa.String(length=255), nullable=True),
        sa.Column('password_reset_expires', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_users_email', 'users', ['email'], unique=True)
    op.create_index('idx_users_role', 'users', ['role'])
    op.create_index('idx_users_status', 'users', ['status'])
    op.create_index('idx_users_sso_subject', 'users', ['sso_subject'], unique=True)

    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('api_key_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=True),
        sa.Column('resource_id', sa.String(length=100), nullable=True),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('path', sa.String(length=500), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('request_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('response_status', sa.SmallInteger(), nullable=False),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_audit_user_id', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('idx_audit_resource', 'audit_logs', ['resource_type', 'resource_id'])

    # Create resource_quotas table
    op.create_table(
        'resource_quotas',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('max_documents', sa.Integer(), nullable=False, server_default='1000'),
        sa.Column('max_storage_bytes', sa.BigInteger(), nullable=False, server_default='10737418240'),
        sa.Column('max_agent_sessions_per_day', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('current_documents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_storage_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('current_agent_sessions_today', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_reset_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )

    # Create retention_policies table
    op.create_table(
        'retention_policies',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('retention_days', sa.Integer(), nullable=False),
        sa.Column('archive_before_delete', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('match_criteria', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create saml_configs table
    op.create_table(
        'saml_configs',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.String(length=500), nullable=False),
        sa.Column('sso_url', sa.String(length=500), nullable=False),
        sa.Column('slo_url', sa.String(length=500), nullable=True),
        sa.Column('x509_cert', sa.Text(), nullable=False),
        sa.Column('metadata_url', sa.String(length=500), nullable=True),
        sa.Column('attribute_mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('role_mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('jit_provisioning', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entity_id')
    )

    # Add user_id to agent_sessions for tracking
    op.add_column('agent_sessions', sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=True))
    op.create_foreign_key('fk_agent_sessions_user_id', 'agent_sessions', 'users', ['user_id'], ['id'], ondelete='SET NULL')
    op.create_index('idx_agent_sessions_user_id', 'agent_sessions', ['user_id'])

    # Create default admin user
    op.execute("""
        INSERT INTO users (id, email, full_name, password_hash, role, status)
        VALUES (
            gen_random_uuid()::text,
            'admin@aeimps.local',
            'System Administrator',
            '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5TS8fQOZmJ5Qy',  -- password: admin123
            'admin',
            'active'
        );
    """)


def downgrade() -> None:
    op.drop_index('idx_agent_sessions_user_id', 'agent_sessions')
    op.drop_constraint('fk_agent_sessions_user_id', 'agent_sessions', type_='foreignkey')
    op.drop_column('agent_sessions', 'user_id')
    
    op.drop_table('saml_configs')
    op.drop_table('retention_policies')
    op.drop_table('resource_quotas')
    op.drop_index('idx_audit_resource', 'audit_logs')
    op.drop_index('idx_audit_timestamp', 'audit_logs')
    op.drop_index('idx_audit_action', 'audit_logs')
    op.drop_index('idx_audit_user_id', 'audit_logs')
    op.drop_table('audit_logs')
    op.drop_index('idx_users_sso_subject', 'users')
    op.drop_index('idx_users_status', 'users')
    op.drop_index('idx_users_role', 'users')
    op.drop_index('idx_users_email', 'users')
    op.drop_table('users')
