PRAGMA foreign_keys = ON;

CREATE TABLE tenants (
  tenant_id TEXT PRIMARY KEY,
  name TEXT,
  api_key_hash TEXT UNIQUE,
  active BOOLEAN,
  metadata TEXT,
  created_at TEXT
);

CREATE TABLE organizations (
  org_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  package_name TEXT,
  status TEXT,
  created_at TEXT,
  FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE TABLE tasks (
  task_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  org_id TEXT NOT NULL,
  description TEXT,
  assigned_to TEXT,
  status TEXT,
  result TEXT,
  governance_preset TEXT,
  created_at TEXT,
  FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
  FOREIGN KEY (org_id) REFERENCES organizations(org_id)
);

CREATE TABLE metering_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL,
  org_id TEXT,
  agent_id TEXT,
  event_type TEXT,
  tokens_in INTEGER,
  tokens_out INTEGER,
  timestamp FLOAT,
  metadata TEXT,
  FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

INSERT INTO tenants (tenant_id, name, api_key_hash, active, metadata, created_at) VALUES
  ('tenant_1', 'Acme Co', 'hash_1', 1, '{"tier":"pro"}', '2026-03-01T10:00:00Z'),
  ('tenant_2', 'Beta Co', 'hash_2', 0, '{"tier":"starter"}', '2026-03-02T11:30:00Z');

INSERT INTO organizations (org_id, tenant_id, package_name, status, created_at) VALUES
  ('org_1', 'tenant_1', 'business', 'active', '2026-03-01T10:01:00Z'),
  ('org_2', 'tenant_2', 'starter', 'paused', '2026-03-02T11:31:00Z');

INSERT INTO tasks (task_id, tenant_id, org_id, description, assigned_to, status, result, governance_preset, created_at) VALUES
  ('task_1', 'tenant_1', 'org_1', 'Migrate data', 'agent_a', 'done', '{"ok":true}', 'default', '2026-03-03T08:00:00Z'),
  ('task_2', 'tenant_1', 'org_1', 'Backfill costs', 'agent_b', 'running', NULL, 'strict', '2026-03-03T09:00:00Z'),
  ('task_3', 'tenant_2', 'org_2', 'Generate report', NULL, 'queued', NULL, 'default', '2026-03-03T10:00:00Z');

INSERT INTO metering_events (tenant_id, org_id, agent_id, event_type, tokens_in, tokens_out, timestamp, metadata) VALUES
  ('tenant_1', 'org_1', 'agent_a', 'completion', 300, 120, 1772800000.5, '{"model":"gpt-5"}'),
  ('tenant_1', 'org_1', 'agent_b', 'completion', 100, 80, 1772800300.0, '{"model":"gpt-5-mini"}'),
  ('tenant_2', 'org_2', 'agent_c', 'prompt', 50, 0, 1772801000.0, '{"model":"gpt-5-mini"}');
