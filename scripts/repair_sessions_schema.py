import os
import sqlite3

DB = os.path.join(os.getcwd(), "erp_pos.db")
conn = sqlite3.connect(DB)
cur = conn.cursor()


def table_exists(name):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def cols(name):
    cur.execute(f"PRAGMA table_info('{name}')")
    return [r[1] for r in cur.fetchall()]


def ensure_col(table, col, decl):
    c = cols(table)
    if col not in c:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {decl}")


# 1) POS SESSION
if not table_exists("pos_session"):
    cur.execute(
        """
    CREATE TABLE pos_session (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        status VARCHAR(20),
        opened_at DATETIME,
        closed_at DATETIME,
        opened_by VARCHAR(60),
        closed_by VARCHAR(60),
        note VARCHAR(255),
        expected_cash NUMERIC(12,2) DEFAULT 0,
        counted_pre NUMERIC(12,2) DEFAULT 0,
        counted_final NUMERIC(12,2) DEFAULT 0,
        diff_cash NUMERIC(12,2) DEFAULT 0,
        tolerance NUMERIC(12,2) DEFAULT 0,
        idem_open VARCHAR(80),
        idem_close VARCHAR(80)
    )
    """
    )
else:
    ensure_col("pos_session", "status", "status VARCHAR(20)")
    ensure_col("pos_session", "opened_at", "opened_at DATETIME")
    ensure_col("pos_session", "closed_at", "closed_at DATETIME")
    ensure_col("pos_session", "opened_by", "opened_by VARCHAR(60)")
    ensure_col("pos_session", "closed_by", "closed_by VARCHAR(60)")
    ensure_col("pos_session", "note", "note VARCHAR(255)")
    ensure_col("pos_session", "expected_cash", "expected_cash NUMERIC(12,2) DEFAULT 0")
    ensure_col("pos_session", "counted_pre", "counted_pre NUMERIC(12,2) DEFAULT 0")
    ensure_col("pos_session", "counted_final", "counted_final NUMERIC(12,2) DEFAULT 0")
    ensure_col("pos_session", "diff_cash", "diff_cash NUMERIC(12,2) DEFAULT 0")
    ensure_col("pos_session", "tolerance", "tolerance NUMERIC(12,2) DEFAULT 0")
    ensure_col("pos_session", "idem_open", "idem_open VARCHAR(80)")
    ensure_col("pos_session", "idem_close", "idem_close VARCHAR(80)")

# 2) CASH COUNT
if not table_exists("cash_count"):
    cur.execute(
        """
    CREATE TABLE cash_count (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        kind VARCHAR(10) NOT NULL,
        total NUMERIC(12,2) DEFAULT 0,
        details_json TEXT,
        at DATETIME,
        by_user VARCHAR(60)
    )
    """
    )
else:
    ensure_col("cash_count", "session_id", "session_id INTEGER")
    ensure_col("cash_count", "kind", "kind VARCHAR(10)")
    ensure_col("cash_count", "total", "total NUMERIC(12,2) DEFAULT 0")
    ensure_col("cash_count", "details_json", "details_json TEXT")
    ensure_col("cash_count", "at", "at DATETIME")
    ensure_col("cash_count", "by_user", "by_user VARCHAR(60)")

# 3) POS ORDER: asegurar columna session_id
if table_exists("pos_order"):
    if "session_id" not in cols("pos_order"):
        cur.execute("ALTER TABLE pos_order ADD COLUMN session_id INTEGER")

conn.commit()
conn.close()
print("SESSION_SCHEMA_OK")
