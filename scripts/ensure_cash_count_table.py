import os
import sqlite3

from app.db import engine

db_path = engine.url.database
if not os.path.isabs(db_path):
    db_path = os.path.abspath(db_path)

conn = sqlite3.connect(db_path)
cur = conn.cursor()


def table_exists(name):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def cols(name):
    cur.execute(f"PRAGMA table_info('{name}')")
    return [(r[1], (r[2] or "").upper()) for r in cur.fetchall()]  # (name, type)


def ensure_col(table, col, decl):
    existing = [c[0] for c in cols(table)]
    if col not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {decl}")


# 1) Crear cash_count si no existe
if not table_exists("cash_count"):
    cur.execute(
        """
        CREATE TABLE cash_count(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            kind VARCHAR(10) NOT NULL,          -- 'pre' | 'final'
            total NUMERIC(12,2) DEFAULT 0,
            details_json TEXT,
            at DATETIME,
            by_user VARCHAR(60)
        )
    """
    )

# 2) Si existe, asegurar columnas clave
else:
    ensure_col("cash_count", "session_id", "session_id INTEGER")
    ensure_col("cash_count", "kind", "kind VARCHAR(10)")
    ensure_col("cash_count", "total", "total NUMERIC(12,2)")
    ensure_col("cash_count", "details_json", "details_json TEXT")
    ensure_col("cash_count", "at", "at DATETIME")
    ensure_col("cash_count", "by_user", "by_user VARCHAR(60)")

conn.commit()
conn.close()
print("CASH_COUNT_OK")
