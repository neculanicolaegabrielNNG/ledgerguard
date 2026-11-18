CREATE TABLE audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE INDEX idx_audit_entity ON audit_log (entity_type, entity_id);

-- ————————————————————————————————————————

CREATE INDEX idx_audit_action ON audit_log (action);

-- ————————————————————————————————————————

CREATE INDEX idx_audit_correlation ON audit_log (correlation_id);

-- ————————————————————————————————————————

CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

-- ————————————————————————————————————————

CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

-- ————————————————————————————————————————

CREATE TABLE webhooks (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    events TEXT NOT NULL,
    secret TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE TABLE webhook_deliveries (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    webhook_id TEXT NOT NULL REFERENCES webhooks (id),
    event TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_status_code INTEGER,
    created_at TEXT NOT NULL,
    delivered_at TEXT
);

-- ————————————————————————————————————————

CREATE INDEX idx_webhook_deliveries_status ON webhook_deliveries (status);
