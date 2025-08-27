import os, sqlite3
from app.db import engine

db = engine.url.database
if not os.path.isabs(db):
    db = os.path.abspath(db)

con = sqlite3.connect(db)
cur = con.cursor()
rows = cur.execute("""
SELECT coupon_id, event, notes, COUNT(*) c
FROM coupon_audit
WHERE event='used'
GROUP BY coupon_id, event, notes
HAVING c > 1
""").fetchall()
print("DUPES_USED =", len(rows))
for r in rows:
    print(r)
con.close()
