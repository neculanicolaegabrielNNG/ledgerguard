CREATE TABLE transfers (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL REFERENCES customers (id),
    from_account_id TEXT NOT NULL REFERENCES accounts (id),
    to_account_id TEXT NOT NULL REFERENCES accounts (id),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    currency TEXT NOT NULL,
    target_amount_minor INTEGER NOT NULL CHECK (target_amount_minor > 0),
    target_currency TEXT NOT NULL,
    amount_ron_minor INTEGER NOT NULL,
    spread_bps INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL CHECK (state IN
        ('created', 'evaluated', 'approved', 'under_review', 'blocked', 'completed', 'cancelled')),
    description TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT 'api' CHECK (channel IN ('api', 'scheduled', 'assistant')),
    risk_score INTEGER,
    decision TEXT,
    transaction_id TEXT,
    correlation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE INDEX idx_transfers_customer ON transfers (customer_id, seq);

-- ————————————————————————————————————————

CREATE INDEX idx_transfers_from ON transfers (from_account_id);

-- ————————————————————————————————————————

CREATE INDEX idx_transfers_to ON transfers (to_account_id);

-- ————————————————————————————————————————

CREATE INDEX idx_transfers_state ON transfers (state);

-- ————————————————————————————————————————

CREATE INDEX idx_transfers_created ON transfers (created_at);

-- ————————————————————————————————————————

CREATE TABLE transfer_transitions (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_id TEXT NOT NULL REFERENCES transfers (id),
    from_state TEXT,
    to_state TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE INDEX idx_transitions_transfer ON transfer_transitions (transfer_id, seq);

-- ————————————————————————————————————————

CREATE TRIGGER transfer_transitions_no_update BEFORE UPDATE ON transfer_transitions
BEGIN
    SELECT RAISE(ABORT, 'transfer_transitions is append-only');
END;

-- ————————————————————————————————————————

CREATE TRIGGER transfer_transitions_no_delete BEFORE DELETE ON transfer_transitions
BEGIN
    SELECT RAISE(ABORT, 'transfer_transitions is append-only');
END;

-- ————————————————————————————————————————

CREATE TABLE scheduled_payments (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL REFERENCES customers (id),
    from_account_id TEXT NOT NULL REFERENCES accounts (id),
    to_account_id TEXT NOT NULL REFERENCES accounts (id),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    description TEXT NOT NULL DEFAULT '',
    interval_seconds INTEGER NOT NULL CHECK (interval_seconds >= 60),
    next_run_at TEXT NOT NULL,
    ends_at TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    last_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE INDEX idx_scheduled_due ON scheduled_payments (active, next_run_at);
