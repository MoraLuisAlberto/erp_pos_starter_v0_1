from app.db import engine
import os, sqlite3, json

db = engine.url.database
if not os.path.isabs(db):
    db = os.path.abspath(db)

con = sqlite3.connect(db)
cur = con.cursor()
rows = cur.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='trigger'").fetchall()
print(json.dumps(rows))
con.close()
