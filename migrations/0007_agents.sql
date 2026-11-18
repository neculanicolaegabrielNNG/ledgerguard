CREATE TABLE agent_reports (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    transfer_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    recommendation TEXT NOT NULL CHECK (recommendation IN ('approve', 'block', 'escalate')),
    confidence REAL NOT NULL,
    report TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE INDEX idx_agent_reports_case ON agent_reports (case_id, seq);

-- ————————————————————————————————————————

CREATE TABLE assistant_actions (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'rejected', 'expired')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    resolved_at TEXT
);
