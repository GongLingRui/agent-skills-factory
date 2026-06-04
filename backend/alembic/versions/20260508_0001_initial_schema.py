"""Initial PostgreSQL schema (docs/17-data-models.md).

Revision ID: 20260508_0001
Revises:
Create Date: 2026-05-08
"""

from __future__ import annotations

from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from dateutil.relativedelta import relativedelta

revision: str = "20260508_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base_tables() -> list[str]:
    return [
        """
        CREATE TABLE roles (
            id VARCHAR(32) PRIMARY KEY,
            name VARCHAR(64) NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE permissions (
            id VARCHAR(32) PRIMARY KEY,
            name VARCHAR(64) NOT NULL,
            resource VARCHAR(32) NOT NULL,
            action VARCHAR(16) NOT NULL
        )
        """,
        """
        CREATE TABLE role_permissions (
            role_id VARCHAR(32) NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_id VARCHAR(32) NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
            PRIMARY KEY (role_id, permission_id)
        )
        """,
        """
        CREATE TABLE user_roles (
            user_id_hash VARCHAR(64) NOT NULL,
            role_id VARCHAR(32) NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            department VARCHAR(64),
            granted_by VARCHAR(64),
            granted_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (user_id_hash, role_id, department)
        )
        """,
        """
        CREATE TABLE agent_apps (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            description TEXT,
            version VARCHAR(32) NOT NULL,
            runspec_schema_version INT DEFAULT 1,
            owner VARCHAR(64),
            lifecycle_state VARCHAR(16) DEFAULT 'active',
            release_config JSONB,
            model_policy JSONB,
            skill_config JSONB,
            tools_allow JSONB,
            knowledge_scopes JSONB,
            output_schema VARCHAR(64),
            limits_config JSONB,
            concurrency_config JSONB,
            audit_config JSONB,
            enterprise_config JSONB,
            tags JSONB,
            ui_config JSONB,
            degradation_exempt BOOLEAN DEFAULT false,
            cold_since TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            created_by VARCHAR(64)
        )
        """,
        """
        CREATE TABLE agent_versions (
            agent_id VARCHAR(64) NOT NULL,
            version VARCHAR(32) NOT NULL,
            name VARCHAR(128) NOT NULL,
            description TEXT,
            instruction TEXT,
            release_config JSONB,
            model_policy JSONB,
            skill_config JSONB,
            tools_allow JSONB,
            knowledge_scopes JSONB,
            output_schema VARCHAR(64),
            limits_config JSONB,
            concurrency_config JSONB,
            audit_config JSONB,
            enterprise_config JSONB,
            tags JSONB,
            ui_config JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            created_by VARCHAR(64),
            PRIMARY KEY (agent_id, version)
        )
        """,
        """
        CREATE TABLE skills (
            id VARCHAR(64) NOT NULL,
            version VARCHAR(32) NOT NULL,
            name VARCHAR(128),
            description TEXT,
            when_to_use TEXT,
            owner VARCHAR(64),
            risk_tier VARCHAR(16),
            skill_package_hash VARCHAR(64),
            storage_path VARCHAR(256),
            status VARCHAR(16) DEFAULT 'active',
            deprecated_at TIMESTAMP,
            deprecated_by VARCHAR(64),
            created_at TIMESTAMP DEFAULT NOW(),
            created_by VARCHAR(64),
            PRIMARY KEY (id, version)
        )
        """,
        """
        CREATE TABLE tools (
            id VARCHAR(64) PRIMARY KEY,
            version VARCHAR(32),
            name VARCHAR(128),
            description TEXT,
            input_schema JSONB,
            output_schema JSONB,
            permission_required JSONB,
            timeout_seconds INT,
            rate_limit JSONB,
            implementation JSONB,
            status VARCHAR(16) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE run_specs (
            run_id VARCHAR(64) PRIMARY KEY,
            runspec_schema_version INT,
            agent_id VARCHAR(64),
            agent_version VARCHAR(32),
            skill_id VARCHAR(64),
            skill_version VARCHAR(32),
            skill_package_hash VARCHAR(64),
            skill_file_manifest JSONB,
            user_id_hash VARCHAR(64) NOT NULL,
            department VARCHAR(64),
            prompt_parts JSONB,
            lazy_references JSONB,
            indexed_references JSONB,
            allowed_tools JSONB,
            retrieval_scopes JSONB,
            script_hooks JSONB,
            output_schema VARCHAR(64),
            runtime JSONB,
            audit JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE sessions (
            session_id VARCHAR(64) PRIMARY KEY,
            run_id VARCHAR(64) NOT NULL REFERENCES run_specs(run_id) ON DELETE CASCADE,
            user_id_hash VARCHAR(64) NOT NULL,
            agent_id VARCHAR(64) NOT NULL,
            department VARCHAR(64),
            status VARCHAR(16) DEFAULT 'created',
            turn_count INT DEFAULT 0,
            total_tokens INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            last_activity TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE checkpoints (
            checkpoint_id VARCHAR(64) PRIMARY KEY,
            run_id VARCHAR(64) NOT NULL,
            session_id VARCHAR(64) NOT NULL,
            turn_number INT NOT NULL,
            timestamp TIMESTAMP DEFAULT NOW(),
            messages JSONB,
            token_count INT,
            tool_calls_so_far JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE agent_usage_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id_hash VARCHAR(64),
            salt_version VARCHAR(8),
            agent_id VARCHAR(64),
            date DATE,
            count INT DEFAULT 1,
            retention_until TIMESTAMP
        )
        """,
        """
        CREATE TABLE feedback_logs (
            id BIGSERIAL PRIMARY KEY,
            session_id VARCHAR(64),
            message_id VARCHAR(64),
            run_id VARCHAR(64),
            agent_id VARCHAR(64),
            feedback VARCHAR(16),
            reasons JSONB,
            comment TEXT,
            timestamp TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE token_quotas (
            id BIGSERIAL PRIMARY KEY,
            scope VARCHAR(16) NOT NULL,
            scope_id VARCHAR(64) NOT NULL,
            budget_tokens BIGINT NOT NULL,
            used_tokens BIGINT DEFAULT 0,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (scope, scope_id, period_start)
        )
        """,
        """
        CREATE TABLE file_uploads (
            file_id VARCHAR(64) PRIMARY KEY,
            session_id VARCHAR(64) NOT NULL,
            user_id_hash VARCHAR(64) NOT NULL,
            file_name VARCHAR(256) NOT NULL,
            file_size BIGINT NOT NULL,
            mime_type VARCHAR(64) NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            storage_path VARCHAR(512),
            status VARCHAR(16) DEFAULT 'pending',
            extracted_text_path VARCHAR(512),
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE daily_stats (
            id BIGSERIAL PRIMARY KEY,
            date DATE NOT NULL,
            agent_id VARCHAR(64) DEFAULT '',
            department VARCHAR(64) DEFAULT '',
            request_count INT DEFAULT 0,
            error_count INT DEFAULT 0,
            p99_latency_ms INT,
            token_input BIGINT DEFAULT 0,
            token_output BIGINT DEFAULT 0,
            model_distribution JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (date, agent_id, department)
        )
        """,
        """
        CREATE TABLE platform_policies (
            lineage_id VARCHAR(32) NOT NULL,
            version INT NOT NULL,
            prompt TEXT NOT NULL,
            enabled BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (lineage_id, version)
        )
        """,
        """
        CREATE TABLE org_policies (
            lineage_id VARCHAR(32) NOT NULL,
            department VARCHAR(64) NOT NULL,
            version INT NOT NULL,
            prompt TEXT NOT NULL,
            enabled BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (lineage_id, version),
            UNIQUE (department, lineage_id, version)
        )
        """,
        """
        CREATE TABLE config_change_logs (
            id BIGSERIAL PRIMARY KEY,
            table_name VARCHAR(64) NOT NULL,
            record_id VARCHAR(64) NOT NULL,
            action VARCHAR(16) NOT NULL,
            old_value JSONB,
            new_value JSONB,
            change_reason TEXT,
            operator_id VARCHAR(64) NOT NULL,
            operator_ip VARCHAR(64),
            timestamp TIMESTAMP DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE degradation_events (
            id BIGSERIAL PRIMARY KEY,
            level INT NOT NULL,
            previous_level INT NOT NULL,
            trigger VARCHAR(32) NOT NULL,
            reason TEXT,
            operator_id VARCHAR(64),
            metrics_snapshot JSONB,
            started_at TIMESTAMP NOT NULL,
            recovered_at TIMESTAMP,
            expected_duration_minutes INT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE token_quota_history (
            id BIGSERIAL PRIMARY KEY,
            scope VARCHAR(16) NOT NULL,
            scope_id VARCHAR(64) NOT NULL,
            previous_budget BIGINT,
            new_budget BIGINT NOT NULL,
            change_reason TEXT,
            effective_period VARCHAR(7) NOT NULL,
            effective_immediately BOOLEAN DEFAULT true,
            operator_id VARCHAR(64) NOT NULL,
            timestamp TIMESTAMP DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE daily_feedback_stats (
            id BIGSERIAL PRIMARY KEY,
            date DATE NOT NULL,
            agent_id VARCHAR(64) NOT NULL,
            total_messages INT DEFAULT 0,
            feedback_up INT DEFAULT 0,
            feedback_down INT DEFAULT 0,
            feedback_rate FLOAT DEFAULT 0,
            reason_distribution JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (date, agent_id)
        )
        """,
        """
        CREATE TABLE archive_manifests (
            id BIGSERIAL PRIMARY KEY,
            archive_type VARCHAR(32) NOT NULL,
            file_path VARCHAR(512) NOT NULL,
            file_size_bytes BIGINT,
            record_count BIGINT,
            date_range_start DATE NOT NULL,
            date_range_end DATE NOT NULL,
            checksum_md5 VARCHAR(32),
            checksum_sha256 VARCHAR(64),
            archived_at TIMESTAMP NOT NULL,
            archived_by VARCHAR(64),
            verified_at TIMESTAMP,
            deleted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE security_events (
            id BIGSERIAL PRIMARY KEY,
            event_type VARCHAR(32) NOT NULL,
            user_id_hash VARCHAR(64),
            agent_id VARCHAR(64),
            session_id VARCHAR(64),
            input_summary TEXT,
            trigger_rule VARCHAR(64),
            queue_priority_before INT,
            queue_priority_after INT,
            timestamp TIMESTAMP DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE system_configs (
            key VARCHAR(128) PRIMARY KEY,
            value JSONB NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT NOW(),
            updated_by VARCHAR(64)
        )
        """,
    ]


def _audit_parent() -> str:
    return """
        CREATE TABLE audit_logs (
            id BIGSERIAL NOT NULL,
            run_id VARCHAR(64),
            session_id VARCHAR(64),
            timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
            level VARCHAR(16),
            user_id_hash VARCHAR(64),
            agent_id VARCHAR(64),
            department VARCHAR(64),
            tool_calls JSONB,
            token_count INT,
            cost FLOAT,
            error_code VARCHAR(32),
            retrieval_ids JSONB,
            prompt_summary TEXT,
            retrieval_hits JSONB,
            full_prompt TEXT,
            full_output TEXT,
            retention_until TIMESTAMP,
            status VARCHAR(16) DEFAULT 'active',
            PRIMARY KEY (id, timestamp)
        ) PARTITION BY RANGE (timestamp)
    """


def _partition_name(d: date) -> str:
    return f"audit_logs_{d.year:04d}_{d.month:02d}"


def _partition_sql(start: date) -> str:
    nxt = start + relativedelta(months=1)
    pname = _partition_name(start)
    return f"""
        CREATE TABLE {pname} PARTITION OF audit_logs
        FOR VALUES FROM (TIMESTAMP '{start.isoformat()} 00:00:00')
        TO (TIMESTAMP '{nxt.isoformat()} 00:00:00')
    """


def upgrade() -> None:
    for stmt in _base_tables():
        op.execute(sa.text(stmt.strip()))

    op.execute(sa.text(_audit_parent().strip()))

    base_month = date.today().replace(day=1)
    for i in range(6):
        m = base_month + relativedelta(months=i)
        op.execute(sa.text(_partition_sql(m).strip()))

    op.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS audit_logs_default "
            "PARTITION OF audit_logs DEFAULT"
        )
    )

    indexes = [
        "CREATE INDEX idx_agent_apps_owner ON agent_apps(owner)",
        "CREATE INDEX idx_agent_apps_lifecycle ON agent_apps(lifecycle_state, cold_since)",
        (
            "CREATE INDEX idx_agent_apps_degradation ON agent_apps(degradation_exempt) "
            "WHERE degradation_exempt = true"
        ),
        "CREATE INDEX idx_sessions_user ON sessions(user_id_hash, created_at DESC)",
        "CREATE INDEX idx_sessions_agent ON sessions(agent_id, created_at DESC)",
        "CREATE INDEX idx_sessions_status ON sessions(status, expires_at)",
        "CREATE INDEX idx_checkpoints_session ON checkpoints(session_id, turn_number)",
        "CREATE INDEX idx_audit_agent_time ON audit_logs(agent_id, timestamp)",
        "CREATE INDEX idx_audit_run_id ON audit_logs(run_id)",
        "CREATE INDEX idx_agent_usage ON agent_usage_logs(agent_id, date)",
        "CREATE INDEX idx_feedback_agent ON feedback_logs(agent_id, timestamp)",
        (
            "CREATE INDEX idx_config_change_table_record ON "
            "config_change_logs(table_name, record_id, timestamp)"
        ),
        "CREATE INDEX idx_degradation_started ON degradation_events(started_at DESC)",
        (
            "CREATE INDEX idx_quota_history_scope ON "
            "token_quota_history(scope, scope_id, timestamp DESC)"
        ),
        "CREATE INDEX idx_daily_feedback_agent ON daily_feedback_stats(agent_id, date DESC)",
        "CREATE INDEX idx_manifest_type_date ON archive_manifests(archive_type, date_range_start)",
        "CREATE INDEX idx_security_events_user ON security_events(user_id_hash, timestamp)",
        "CREATE INDEX idx_security_events_type ON security_events(event_type, timestamp)",
        "CREATE INDEX idx_file_uploads_session ON file_uploads(session_id)",
        "CREATE INDEX idx_file_uploads_sha256 ON file_uploads(sha256)",
    ]
    for idx in indexes:
        op.execute(sa.text(idx))


_DROP_ORDER = [
    "system_configs",
    "security_events",
    "archive_manifests",
    "daily_feedback_stats",
    "token_quota_history",
    "degradation_events",
    "config_change_logs",
    "org_policies",
    "platform_policies",
    "daily_stats",
    "file_uploads",
    "token_quotas",
    "feedback_logs",
    "agent_usage_logs",
    "audit_logs",
    "checkpoints",
    "sessions",
    "run_specs",
    "tools",
    "skills",
    "agent_versions",
    "agent_apps",
    "user_roles",
    "role_permissions",
    "permissions",
    "roles",
]


def downgrade() -> None:
    for name in _DROP_ORDER:
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))
