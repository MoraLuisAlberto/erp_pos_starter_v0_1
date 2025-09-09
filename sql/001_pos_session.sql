-- Minimal bootstrap para CI/local
CREATE TABLE IF NOT EXISTS pos_session (
  id INTEGER PRIMARY KEY,
  store_id INTEGER NOT NULL,
  terminal_id INTEGER NOT NULL,
  user_open_id INTEGER NOT NULL,
  opened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status TEXT NOT NULL DEFAULT 'open',
  user_close_id INTEGER,
  closed_at TIMESTAMP,
  idempotency_open TEXT,
  idempotency_close TEXT,
  audit_ref TEXT,
  opened_by TEXT,
  closed_by TEXT,
  note TEXT,
  expected_cash REAL NOT NULL DEFAULT 0,
  counted_pre REAL NOT NULL DEFAULT 0,
  counted_final REAL NOT NULL DEFAULT 0,
  diff_cash REAL NOT NULL DEFAULT 0,
  tolerance REAL NOT NULL DEFAULT 0,
  idem_open TEXT,
  idem_close TEXT
);
