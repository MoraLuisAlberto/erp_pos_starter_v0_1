from app.db import engine
from app.models.pos_session import CashCount

# ORM
orm_table = CashCount.__table__
orm_cols = [(c.name, str(c.type), c.nullable) for c in orm_table.columns]

# DB (SQLite)
import os
import sqlite3

db_path = engine.url.database
if not os.path.isabs(db_path):
    db_path = os.path.abspath(db_path)
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (orm_table.name,))
exists = cur.fetchone() is not None

print("=== ORM ===")
print("table:", orm_table.name)
for n, t, nn in orm_cols:
    print(f"  - {n:15s}  {t:20s}  nullable={nn}")

print("=== DB ===")
print("exists:", exists)
if exists:
    cur.execute(f"PRAGMA table_info('{orm_table.name}')")
    # PRAGMA: cid, name, type, notnull, dflt_value, pk
    for cid, name, ctype, notnull, dflt, pk in cur.fetchall():
        print(f"  - {name:15s}  {ctype:20s}  notnull={notnull}  default={dflt}  pk={pk}")
else:
    print("  (no existe)")

conn.close()
