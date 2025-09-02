from datetime import datetime, timezone
import os
import sqlite3

from app.db import engine


def is_numeric_type(decl: str) -> bool:
    if not decl:
        return False
    decl = decl.upper()
    return any(tok in decl for tok in ["INT", "NUM", "DEC", "REAL", "FLOAT", "DOUBLE"])


db_path = engine.url.database
if not os.path.isabs(db_path):
    db_path = os.path.abspath(db_path)

conn = sqlite3.connect(db_path)
cur = conn.cursor()


def table_exists(name):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def ensure_table_store():
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS store(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(40) UNIQUE,
            name VARCHAR(120) NOT NULL
        )
    """
    )
    cur.execute("SELECT id FROM store ORDER BY id LIMIT 1")
    r = cur.fetchone()
    if r:
        return r[0]
    cur.execute("INSERT INTO store(code,name) VALUES('DEFAULT','Default Store')")
    return cur.lastrowid


def ensure_table_terminal():
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS terminal(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(40) UNIQUE,
            name VARCHAR(120) NOT NULL
        )
    """
    )
    cur.execute("SELECT id FROM terminal ORDER BY id LIMIT 1")
    r = cur.fetchone()
    if r:
        return r[0]
    cur.execute("INSERT INTO terminal(code,name) VALUES('TERM-1','Default Terminal')")
    return cur.lastrowid


store_id = ensure_table_store()
terminal_id = ensure_table_terminal()

# Si no existe pos_session, crea una mínima (luego la adaptamos dinámicamente)
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
        idem_close VARCHAR(80),
        store_id INTEGER,
        terminal_id INTEGER
    )
    """
    )

# Si ya hay una open, úsala
cur.execute("SELECT id FROM pos_session WHERE status='open' ORDER BY id DESC LIMIT 1")
r = cur.fetchone()
if r:
    print(r[0])
    conn.close()
    raise SystemExit(0)

# Leer esquema real de pos_session
cur.execute("PRAGMA table_info('pos_session')")
cols = cur.fetchall()
# PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
col_defs = []
for cid, name, ctype, notnull, dflt, pk in cols:
    col_defs.append({"name": name, "type": ctype or "", "notnull": bool(notnull), "pk": bool(pk)})

# Base de valores
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
base = {
    "status": "open",
    "opened_at": now,
    "opened_by": "demo",
    "note": "seed open",
    "expected_cash": 0,
    "counted_pre": 0,
    "counted_final": 0,
    "diff_cash": 0,
    "tolerance": 0,
    "idem_open": f"seed-open-{int(datetime.now(timezone.utc).timestamp())}",
    "store_id": store_id,
    "terminal_id": terminal_id,
}

# Construir fila cubriendo NOT NULL desconocidos
row = {}
for c in col_defs:
    name = c["name"]
    if name == "id":
        # pk autoincrement
        continue
    if name in base:
        row[name] = base[name]
        continue
    # Si es NOT NULL y no tenemos valor, pone un default genérico
    if c["notnull"]:
        if is_numeric_type(c["type"]):
            row[name] = 0
        else:
            row[name] = ""
    # Si es NULL permitido y no lo conocemos, lo omitimos

# Preparar INSERT dinámico
fields = ", ".join(row.keys())
placeholders = ", ".join(["?"] * len(row))
values = list(row.values())

cur.execute(f"INSERT INTO pos_session ({fields}) VALUES ({placeholders})", values)
sess_id = cur.lastrowid
conn.commit()
conn.close()
print(sess_id)
