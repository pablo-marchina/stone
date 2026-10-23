-- TAPI local research schema; synthetic fixtures only; not production PostgreSQL.
CREATE TABLE IF NOT EXISTS tenants (
          tenant_id TEXT PRIMARY KEY, name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS creators (
          tenant_id TEXT NOT NULL, id TEXT NOT NULL, origin TEXT NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY (tenant_id,id), FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
        );
        CREATE TABLE IF NOT EXISTS content_items (
          tenant_id TEXT NOT NULL, id TEXT NOT NULL, creator_id TEXT NOT NULL,
          origin TEXT NOT NULL, published_at TEXT NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY (tenant_id,id),
          FOREIGN KEY (tenant_id,creator_id) REFERENCES creators(tenant_id,id)
        );
        CREATE TABLE IF NOT EXISTS metrics_snapshots (
          tenant_id TEXT NOT NULL, id TEXT NOT NULL, content_id TEXT NOT NULL,
          observed_at TEXT NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY (tenant_id,id),
          FOREIGN KEY (tenant_id,content_id) REFERENCES content_items(tenant_id,id)
        );
        CREATE TABLE IF NOT EXISTS rubric_assessments (
          tenant_id TEXT NOT NULL, id TEXT NOT NULL, content_id TEXT NOT NULL,
          recorded_at TEXT NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY (tenant_id,id),
          FOREIGN KEY (tenant_id,content_id) REFERENCES content_items(tenant_id,id)
        );
        CREATE TABLE IF NOT EXISTS insights (
          tenant_id TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY (tenant_id,id), FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
        );
        CREATE TABLE IF NOT EXISTS creative_versions (
          tenant_id TEXT NOT NULL, id TEXT NOT NULL, insight_id TEXT NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY (tenant_id,id),
          FOREIGN KEY (tenant_id,insight_id) REFERENCES insights(tenant_id,id)
        );
        CREATE TABLE IF NOT EXISTS domain_events (
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          event_id TEXT NOT NULL UNIQUE, tenant_id TEXT NOT NULL,
          aggregate_type TEXT NOT NULL, aggregate_id TEXT NOT NULL,
          event_type TEXT NOT NULL, aggregate_version INTEGER NOT NULL,
          occurred_at TEXT NOT NULL, payload TEXT NOT NULL,
          UNIQUE(tenant_id, aggregate_type, aggregate_id, aggregate_version)
        );
        CREATE INDEX IF NOT EXISTS idx_content_creator ON content_items(tenant_id,creator_id);
        CREATE INDEX IF NOT EXISTS idx_metrics_content_time ON metrics_snapshots(tenant_id,content_id,observed_at);
        CREATE INDEX IF NOT EXISTS idx_events_tenant_seq ON domain_events(tenant_id,seq);
