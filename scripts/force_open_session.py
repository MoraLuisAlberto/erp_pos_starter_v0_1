import datetime
import os
import sqlite3

from app.db import engine

db_path = engine.url.database
if not os.path.isabs(db_path):
    db_path = os.path.abspath(db_path)

conn = sqlite3.connect(db_path)
cur = conn.cursor()


def table_exists(n):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (n,))
    return cur.fetchone() is not None


def cols(t):
    cur.execute(f"PRAGMA table_info('{t}')")
    return [r[1] for r in cur.fetchall()]


# asegurar store y tienda por defecto
if not table_exists("store"):
    cur.execute(
        "CREATE TABLE store(id INTEGER PRIMARY KEY AUTOINCREMENT, code VARCHAR(40) UNIQUE, name VARCHAR(120) NOT NULL)"
    )
cur.execute("SELECT id FROM store ORDER BY id LIMIT 1")
r = cur.fetchone()
if r is None:
    cur.execute("INSERT INTO store(code,name) VALUES('DEFAULT','Default Store')")
    store_id = cur.lastrowid
else:
    store_id = r[0]

# asegurar pos_session y store_id
if not table_exists("pos_session"):
    cur.execute(
        """CREATE TABLE pos_session(
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
    )"""
    )
if "store_id" not in cols("pos_session"):
    cur.execute("ALTER TABLE pos_session ADD COLUMN store_id INTEGER")

# abrir si no hay
cur.execute("SELECT id FROM pos_session WHERE status='open' ORDER BY id DESC LIMIT 1")
row = cur.fetchone()
if row:
    sid = row[0]
else:
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO pos_session (status,opened_at,opened_by,store_id,note) VALUES (?,?,?,?,?)",
        ("open", now, "demo", store_id, "seed open"),
    )
    sid = cur.lastrowid

conn.commit()
conn.close()
print(sid)
