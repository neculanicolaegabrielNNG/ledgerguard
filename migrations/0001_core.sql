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
