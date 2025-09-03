from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

# Creamos la tabla vacía si no existe y luego agregamos columnas faltantes.
BASE_DDL = """
CREATE TABLE IF NOT EXISTS pos_session (
  id INTEGER PRIMARY KEY AUTOINCREMENT
);
"""

# Columnas que /session/open usa en el INSERT (según uvicorn.log)
REQUIRED_COLS = {
    # nombre: definición
    "store_id": "INTEGER",
    "terminal_id": "INTEGER",
    "user_open_id": "INTEGER",
    "opened_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "status": "TEXT NOT NULL DEFAULT 'open'",
    "user_close_id": "INTEGER",
    "closed_at": "TIMESTAMP",
    "idempotency_open": "TEXT",
    "idempotency_close": "TEXT",
    "audit_ref": "TEXT",
    "opened_by": "TEXT",
    "closed_by": "TEXT",
    "note": "TEXT",
    "expected_cash": "REAL NOT NULL DEFAULT 0",
    "counted_pre": "REAL NOT NULL DEFAULT 0",
    "counted_final": "REAL NOT NULL DEFAULT 0",
    "diff_cash": "REAL NOT NULL DEFAULT 0",
    "tolerance": "REAL NOT NULL DEFAULT 0",
    "idem_open": "TEXT",
    "idem_close": "TEXT",
}


def _sqlite_path_from_database_url(url: str) -> Path:
    if not url:
        return Path("erp.db")
    if url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", "", 1))
    if url.startswith("sqlite:////"):
        return Path(url.replace("sqlite:////", "/", 1))
    parsed = urlparse(url)
    return Path(parsed.path or "./erp.db") if parsed.scheme == "sqlite" else Path("erp.db")


def ensure_table_and_columns(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        # 1) Asegura tabla base
        cur.execute(BASE_DDL)

        # 2) Columnas existentes
        cur.execute("PRAGMA table_info('pos_session')")
        existing = {row[1] for row in cur.fetchall()}  # row[1]=name

        # 3) Agrega faltantes
        for name, decl in REQUIRED_COLS.items():
            if name not in existing:
                cur.execute(f"ALTER TABLE pos_session ADD COLUMN {name} {decl}")

        con.commit()

        # 4) Verifica
        cur.execute("PRAGMA table_info('pos_session')")
        final_cols = {row[1] for row in cur.fetchall()}
        missing = sorted(set(REQUIRED_COLS) - final_cols)
        if missing:
            raise SystemExit(f"pos_session missing columns after bootstrap: {missing}")

        print(f"[bootstrap] pos_session ready in {db_path} with columns: {sorted(final_cols)}")
    finally:
        con.close()


if __name__ == "__main__":
    url = os.getenv("DATABASE_URL", "sqlite:///./erp.db")
    ensure_table_and_columns(_sqlite_path_from_database_url(url))
