from __future__ import annotations
import os, sqlite3
from pathlib import Path
from urllib.parse import urlparse

DDL = """
CREATE TABLE IF NOT EXISTS pos_session (
  id INTEGER PRIMARY KEY AUTOINCREMENT
  -- columnas mínimas se añaden abajo con ALTER si faltan
);
"""

REQUIRED_COLS = {
    "pos_id": "INTEGER",
    "cashier_id": "INTEGER",
    "opening_cash": "REAL NOT NULL DEFAULT 0",
    "status": "TEXT NOT NULL DEFAULT 'open'",
    "opened_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "opened_by": "TEXT",
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
        con.execute("PRAGMA foreign_keys=ON;")
        cur = con.cursor()
        # 1) Asegura la tabla
        cur.execute(DDL)
        # 2) Lee columnas existentes
        cur.execute("PRAGMA table_info('pos_session')")
        existing = {row[1] for row in cur.fetchall()}  # row[1] = name
        # 3) Agrega faltantes
        for name, decl in REQUIRED_COLS.items():
            if name not in existing:
                cur.execute(f"ALTER TABLE pos_session ADD COLUMN {name} {decl}")
        con.commit()
        # 4) Verifica
        cur.execute("PRAGMA table_info('pos_session')")
        final_cols = {row[1] for row in cur.fetchall()}
        missing = [c for c in REQUIRED_COLS if c not in final_cols]
        if missing:
            raise SystemExit(f"pos_session missing columns after bootstrap: {missing}")
        print(f"[bootstrap] pos_session ready in {db_path} with columns: {sorted(final_cols)}")
    finally:
        con.close()


if __name__ == "__main__":
    url = os.getenv("DATABASE_URL", "sqlite:///./erp.db")
    ensure_table_and_columns(_sqlite_path_from_database_url(url))
