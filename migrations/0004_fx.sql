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
