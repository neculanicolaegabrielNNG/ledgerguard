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
