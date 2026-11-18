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
