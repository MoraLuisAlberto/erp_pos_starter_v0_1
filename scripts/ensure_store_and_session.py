import os, sqlite3
from app.db import engine

db_path = engine.url.database
if not os.path.isabs(db_path):
    db_path = os.path.abspath(db_path)

conn = sqlite3.connect(db_path); cur = conn.cursor()

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

# 1) Tabla store (básica)
if not table_exists("store"):
    cur.execute("""
        CREATE TABLE store(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(40) UNIQUE,
            name VARCHAR(120) NOT NULL
        )
    """)
# asegurar tienda por defecto
cur.execute("SELECT id FROM store ORDER BY id LIMIT 1")
row = cur.fetchone()
if row is None:
    cur.execute("INSERT INTO store(code,name) VALUES('DEFAULT','Default Store')")
    default_store_id = cur.lastrowid
else:
    default_store_id = row[0]

# 2) pos_session.store_id (si falta, crearla y rellenar)
if table_exists("pos_session"):
    if "store_id" not in cols("pos_session"):
        cur.execute("ALTER TABLE pos_session ADD COLUMN store_id INTEGER")
    # para nulos, rellena con la tienda por defecto
    cur.execute("UPDATE pos_session SET store_id=? WHERE store_id IS NULL", (default_store_id,))
else:
    # si no existiera, la crea completa con store_id
    cur.execute("""
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
        store_id INTEGER
    )
    """)
    cur.execute("INSERT INTO pos_session(status,opened_by,store_id) VALUES('open','demo',?)", (default_store_id,))

conn.commit(); conn.close()
print(default_store_id)
