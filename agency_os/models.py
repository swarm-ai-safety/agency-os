"""SQLAlchemy table definitions for Agency-OS."""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

tenants = sa.Table(
    "tenants",
    metadata,
    sa.Column("tenant_id", sa.Text, primary_key=True),
    sa.Column("name", sa.Text),
    sa.Column("api_key_hash", sa.Text, unique=True),
    sa.Column("active", sa.Boolean),
    sa.Column("metadata", sa.Text),
    sa.Column("created_at", sa.Text),
)

tenant_sessions = sa.Table(
    "tenant_sessions",
    metadata,
    sa.Column("session_id", sa.Text, primary_key=True),
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False),
    sa.Column("token_hash", sa.Text, nullable=False, unique=True),
    sa.Column("created_at", sa.Float, nullable=False),
    sa.Column("expires_at", sa.Float, nullable=False),
    sa.Column("revoked_at", sa.Float),
    sa.Index("ix_tenant_sessions_tenant_id", "tenant_id"),
    sa.Index("ix_tenant_sessions_expires_at", "expires_at"),
)

organizations = sa.Table(
    "organizations",
    metadata,
    sa.Column("org_id", sa.Text, primary_key=True),
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False),
    sa.Column("package_name", sa.Text),
    sa.Column("status", sa.Text),
    sa.Column("created_at", sa.Text),
)

tasks = sa.Table(
    "tasks",
    metadata,
    sa.Column("task_id", sa.Text, primary_key=True),
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False),
    sa.Column("org_id", sa.Text, sa.ForeignKey("organizations.org_id"), nullable=False),
    sa.Column("description", sa.Text),
    sa.Column("assigned_to", sa.Text),
    sa.Column("status", sa.Text),
    sa.Column("result", sa.Text),
    sa.Column("governance_preset", sa.Text),
    sa.Column("trajectory", sa.Text),
    sa.Column("created_at", sa.Text),
)

metering_events = sa.Table(
    "metering_events",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False),
    sa.Column("org_id", sa.Text),
    sa.Column("agent_id", sa.Text),
    sa.Column("event_type", sa.Text),
    sa.Column("tokens_in", sa.Integer),
    sa.Column("tokens_out", sa.Integer),
    sa.Column("timestamp", sa.Float),
    sa.Column("metadata", sa.Text),
)

wallet_snapshots = sa.Table(
    "wallet_snapshots",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("org_id", sa.Text),
    sa.Column("agent_id", sa.Text),
    sa.Column("balance", sa.Float),
    sa.Column("reputation", sa.Float),
    sa.Column("snapshot_at", sa.Text),
)

trust_scores = sa.Table(
    "trust_scores",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.Text),
    sa.Column("org_id", sa.Text),
    sa.Column("agent_id", sa.Text, nullable=False),
    sa.Column("score", sa.Float, nullable=False),
    sa.Column("tier", sa.Text, nullable=False),
    sa.Column("total_tasks", sa.Integer, nullable=False),
    sa.Column("successes", sa.Integer, nullable=False),
    sa.Column("failures", sa.Integer, nullable=False),
    sa.Column("partials", sa.Integer, nullable=False),
    sa.Column("computed_at", sa.Float, nullable=False),
)

processed_webhook_events = sa.Table(
    "processed_webhook_events",
    metadata,
    sa.Column("event_id", sa.Text, primary_key=True),
    sa.Column("event_type", sa.Text),
    sa.Column("processed_at", sa.Text),
)

waitlist = sa.Table(
    "waitlist",
    metadata,
    sa.Column("email", sa.Text, primary_key=True),
    sa.Column("signed_up_at", sa.Float),
    sa.Column("ip_hash", sa.Text, comment="SHA-256 hash of client IP (not plaintext)"),
)

webhooks = sa.Table(
    "webhooks",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False),
    sa.Column("url", sa.Text, nullable=False),
    sa.Column("events", sa.Text, nullable=False),  # JSON array
    sa.Column("secret_encrypted", sa.Text, nullable=False),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Column("rotated_at", sa.Text),
    sa.UniqueConstraint("tenant_id", "url", name="uq_tenant_webhook_url"),
)

gateway_provider_keys = sa.Table(
    "gateway_provider_keys",
    metadata,
    sa.Column("provider", sa.Text, primary_key=True),
    sa.Column("secret_encrypted", sa.Text, nullable=False),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Column("updated_at", sa.Text, nullable=False),
)

webhook_deliveries = sa.Table(
    "webhook_deliveries",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("webhook_id", sa.Text, sa.ForeignKey("webhooks.id")),
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False),
    sa.Column("org_id", sa.Text),
    sa.Column("url", sa.Text, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("payload_json", sa.Text, nullable=False),
    sa.Column("signature", sa.Text, nullable=False),
    sa.Column("event_timestamp", sa.Integer, nullable=False),
    sa.Column("attempt_count", sa.Integer, nullable=False, server_default=sa.text("0")),
    sa.Column("max_attempts", sa.Integer, nullable=False, server_default=sa.text("5")),
    sa.Column("retryable", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("success", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("status_code", sa.Integer),
    sa.Column("error", sa.Text),
    sa.Column("next_retry_at", sa.Text),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Column("updated_at", sa.Text, nullable=False),
    sa.Column("completed_at", sa.Text),
    sa.Index(
        "ix_webhook_deliveries_retry_due", "success", "retryable", "next_retry_at"
    ),
    sa.Index(
        "ix_webhook_deliveries_tenant_webhook", "tenant_id", "webhook_id", "created_at"
    ),
)

audit_log = sa.Table(
    "audit_log",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.Text),
    sa.Column("actor", sa.Text, nullable=False),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("resource", sa.Text),
    sa.Column("resource_id", sa.Text),
    sa.Column("detail", sa.Text),
    sa.Column("timestamp", sa.Float, nullable=False),
)

timeline_events = sa.Table(
    "timeline_events",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False),
    sa.Column("org_id", sa.Text, sa.ForeignKey("organizations.org_id"), nullable=False),
    sa.Column("agent_id", sa.Text),
    sa.Column("agent_name", sa.Text),
    sa.Column("agent_division", sa.Text),
    sa.Column("agent_color", sa.Text),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("detail", sa.Text),
    sa.Column("artifact_type", sa.Text),
    sa.Column("artifact_ref", sa.Text),
    sa.Column("budget_snapshot", sa.Float),
    sa.Column("reputation_snapshot", sa.Float),
    sa.Column("metadata_json", sa.Text),
    sa.Column("timestamp", sa.Float, nullable=False),
    sa.Index("ix_timeline_events_org_ts", "org_id", "timestamp"),
    sa.Index("ix_timeline_events_tenant_org", "tenant_id", "org_id"),
)

tenant_provider_keys = sa.Table(
    "tenant_provider_keys",
    metadata,
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False),
    sa.Column("provider", sa.Text, nullable=False),
    sa.Column("secret_encrypted", sa.Text, nullable=False),
    sa.Column("key_fingerprint", sa.Text, nullable=False),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Column("updated_at", sa.Text, nullable=False),
    sa.PrimaryKeyConstraint("tenant_id", "provider"),
)

gateway_requests = sa.Table(
    "gateway_requests",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("request_id", sa.Text, unique=True),
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False),
    sa.Column("model_id", sa.Text),
    sa.Column("provider", sa.Text),
    sa.Column("tokens_in", sa.Integer),
    sa.Column("tokens_out", sa.Integer),
    sa.Column("latency_ms", sa.Float),
    sa.Column("provider_cost", sa.Float),
    sa.Column("customer_cost", sa.Float),
    sa.Column("margin", sa.Float),
    sa.Column("cached", sa.Boolean, server_default=sa.false()),
    sa.Column("routed_by", sa.Text),
    sa.Column("complexity", sa.Text),
    sa.Column("status", sa.Text),
    sa.Column("timestamp", sa.Float),
)
