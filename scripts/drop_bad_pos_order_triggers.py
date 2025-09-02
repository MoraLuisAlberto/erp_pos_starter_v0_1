import os
import sqlite3

from app.db import engine

db = engine.url.database
if not os.path.isabs(db):
    db = os.path.abspath(db)

con = sqlite3.connect(db)
cur = con.cursor()

trigs = cur.execute(
    "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='pos_order'"
).fetchall()

dropped = []
for name, sql in trigs:
    if sql and "NEW.closed_by" in sql:
        cur.execute(f'DROP TRIGGER IF EXISTS "{name}"')
        dropped.append(name)

con.commit()
con.close()

print("DROPPED:", ",".join(dropped) if dropped else "(none)")
