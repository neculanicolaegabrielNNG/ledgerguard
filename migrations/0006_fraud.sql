CREATE TABLE fraud_rules (
    id TEXT NOT NULL,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    params TEXT NOT NULL,
    priority INTEGER NOT NULL,
    effect TEXT NOT NULL CHECK (effect IN ('score_add', 'review', 'block')),
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    valid_from TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    PRIMARY KEY (id, version)
);

-- ————————————————————————————————————————

CREATE TRIGGER fraud_rules_no_update BEFORE UPDATE ON fraud_rules
BEGIN
    SELECT RAISE(ABORT, 'fraud_rules is append-only');
END;

-- ————————————————————————————————————————

CREATE TRIGGER fraud_rules_no_delete BEFORE DELETE ON fraud_rules
BEGIN
    SELECT RAISE(ABORT, 'fraud_rules is append-only');
END;

-- ————————————————————————————————————————

CREATE TABLE fraud_evaluations (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    transfer_id TEXT NOT NULL,
    score INTEGER NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approve', 'review', 'block')),
    results TEXT NOT NULL,
    thresholds TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE INDEX idx_evaluations_transfer ON fraud_evaluations (transfer_id);

-- ————————————————————————————————————————

CREATE TRIGGER fraud_evaluations_no_update BEFORE UPDATE ON fraud_evaluations
BEGIN
    SELECT RAISE(ABORT, 'fraud_evaluations is append-only');
END;

-- ————————————————————————————————————————

CREATE TRIGGER fraud_evaluations_no_delete BEFORE DELETE ON fraud_evaluations
BEGIN
    SELECT RAISE(ABORT, 'fraud_evaluations is append-only');
END;

-- ————————————————————————————————————————

CREATE TABLE fraud_cases (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    transfer_id TEXT NOT NULL UNIQUE,
    evaluation_id TEXT NOT NULL REFERENCES fraud_evaluations (id),
    score INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'escalated', 'resolved')),
    resolution TEXT CHECK (resolution IN ('approve', 'block', 'cancelled')),
    opened_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT,
    comment TEXT
);

-- ————————————————————————————————————————

CREATE INDEX idx_cases_queue ON fraud_cases (status, score DESC, seq);

-- ————————————————————————————————————————

CREATE TABLE fraud_case_actions (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES fraud_cases (id),
    action TEXT NOT NULL,
    comment TEXT NOT NULL,
    actor TEXT NOT NULL,
    at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE TRIGGER fraud_case_actions_no_update BEFORE UPDATE ON fraud_case_actions
BEGIN
    SELECT RAISE(ABORT, 'fraud_case_actions is append-only');
END;
