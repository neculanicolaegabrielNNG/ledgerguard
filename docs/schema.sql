CREATE TABLE customers (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE TABLE users (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('customer', 'compliance', 'admin')),
    customer_id TEXT REFERENCES customers (id),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE TABLE accounts (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    customer_id TEXT REFERENCES customers (id),
    currency TEXT NOT NULL CHECK (currency IN ('RON', 'EUR', 'USD', 'CHF')),
    kind TEXT NOT NULL CHECK (kind IN ('customer', 'system_cash', 'fx_exchange')),
    system_key TEXT UNIQUE,
    name TEXT NOT NULL,
    allow_negative INTEGER NOT NULL DEFAULT 0 CHECK (allow_negative IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    created_at TEXT NOT NULL,
    CHECK ((kind = 'customer' AND customer_id IS NOT NULL) OR (kind <> 'customer' AND customer_id IS NULL))
);

-- ————————————————————————————————————————

CREATE INDEX idx_accounts_customer ON accounts (customer_id);

-- ————————————————————————————————————————

CREATE TRIGGER accounts_no_delete BEFORE DELETE ON accounts
BEGIN
    SELECT RAISE(ABORT, 'accounts cannot be deleted');
END;

-- ————————————————————————————————————————

CREATE TABLE idempotency_keys (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (scope, key)
);

-- ————————————————————————————————————————

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

-- ————————————————————————————————————————

CREATE TABLE transactions (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('deposit', 'transfer', 'reversal')),
    description TEXT NOT NULL DEFAULT '',
    transfer_id TEXT,
    reverses_id TEXT UNIQUE REFERENCES transactions (id),
    ron_residual_minor INTEGER NOT NULL DEFAULT 0,
    correlation_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE TABLE ledger_entries (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NOT NULL REFERENCES transactions (id),
    account_id TEXT NOT NULL REFERENCES accounts (id),
    currency TEXT NOT NULL CHECK (currency IN ('RON', 'EUR', 'USD', 'CHF')),
    amount_minor INTEGER NOT NULL CHECK (amount_minor <> 0),
    amount_ron_minor INTEGER NOT NULL,
    fx_rate_e8 INTEGER NOT NULL CHECK (fx_rate_e8 > 0),
    fx_rate_id TEXT,
    fx_rate_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE INDEX idx_entries_account ON ledger_entries (account_id, seq);

-- ————————————————————————————————————————

CREATE INDEX idx_entries_transaction ON ledger_entries (transaction_id);

-- ————————————————————————————————————————

CREATE INDEX idx_entries_created ON ledger_entries (created_at);

-- ————————————————————————————————————————

CREATE TRIGGER ledger_entries_no_update BEFORE UPDATE ON ledger_entries
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only');
END;

-- ————————————————————————————————————————

CREATE TRIGGER ledger_entries_no_delete BEFORE DELETE ON ledger_entries
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only');
END;

-- ————————————————————————————————————————

CREATE TRIGGER transactions_no_update BEFORE UPDATE ON transactions
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only');
END;

-- ————————————————————————————————————————

CREATE TRIGGER transactions_no_delete BEFORE DELETE ON transactions
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only');
END;

-- ————————————————————————————————————————

CREATE TRIGGER ledger_entries_currency_match BEFORE INSERT ON ledger_entries
WHEN (SELECT currency FROM accounts WHERE id = NEW.account_id) IS NOT NEW.currency
BEGIN
    SELECT RAISE(ABORT, 'entry currency must match account currency');
END;

-- ————————————————————————————————————————

CREATE TABLE fx_rates (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    base TEXT NOT NULL CHECK (base IN ('EUR', 'USD', 'CHF')),
    quote TEXT NOT NULL CHECK (quote = 'RON'),
    rate_e8 INTEGER NOT NULL CHECK (rate_e8 > 0),
    valid_from TEXT NOT NULL,
    source TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE INDEX idx_fx_rates_lookup ON fx_rates (base, valid_from);

-- ————————————————————————————————————————

CREATE TRIGGER fx_rates_no_update BEFORE UPDATE ON fx_rates
BEGIN
    SELECT RAISE(ABORT, 'fx_rates is append-only');
END;

-- ————————————————————————————————————————

CREATE TRIGGER fx_rates_no_delete BEFORE DELETE ON fx_rates
BEGIN
    SELECT RAISE(ABORT, 'fx_rates is append-only');
END;

-- ————————————————————————————————————————

CREATE TABLE fx_alerts (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    currency TEXT NOT NULL,
    previous_rate_e8 INTEGER NOT NULL,
    proposed_rate_e8 INTEGER NOT NULL,
    change_bps INTEGER NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE INDEX idx_fx_alerts_currency ON fx_alerts (currency, created_at);

-- ————————————————————————————————————————

CREATE TRIGGER fx_alerts_no_update BEFORE UPDATE ON fx_alerts
BEGIN
    SELECT RAISE(ABORT, 'fx_alerts is append-only');
END;

-- ————————————————————————————————————————

CREATE TRIGGER fx_alerts_no_delete BEFORE DELETE ON fx_alerts
BEGIN
    SELECT RAISE(ABORT, 'fx_alerts is append-only');
END;

-- ————————————————————————————————————————

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

-- ————————————————————————————————————————

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

-- ————————————————————————————————————————

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

-- ————————————————————————————————————————

CREATE TABLE simulation_runs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    strategy TEXT NOT NULL,
    seed INTEGER NOT NULL,
    benign_count INTEGER NOT NULL,
    metrics TEXT NOT NULL,
    steps TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE TABLE test_runs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_label TEXT NOT NULL,
    suite TEXT NOT NULL,
    test TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PASS', 'FAIL', 'SKIP')),
    message TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    recorded_at TEXT NOT NULL
);

-- ————————————————————————————————————————

CREATE INDEX idx_test_runs_test ON test_runs (suite, test, seq);

-- ————————————————————————————————————————

CREATE TABLE test_proposals (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL,
    UNIQUE (kind, title)
);
