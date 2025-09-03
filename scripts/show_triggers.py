import json
import os
import sqlite3

from app.db import engine

db = engine.url.database
if not os.path.isabs(db):
    db = os.path.abspath(db)

con = sqlite3.connect(db)
cur = con.cursor()
rows = cur.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='trigger'").fetchall()
print(json.dumps(rows))
con.close()
