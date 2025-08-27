import os, sqlite3, json
from app.db import engine

db_path = engine.url.database
if not os.path.isabs(db_path):
    db_path = os.path.abspath(db_path)

con = sqlite3.connect(db_path)
cur = con.cursor()

def cols(table):
    return [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]

tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
info = {t: cols(t) for t in tables}

print(json.dumps(info, indent=2))
con.close()
