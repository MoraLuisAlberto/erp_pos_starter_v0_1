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
GROUP BY coupon_id, event, notes
HAVING c > 1
ORDER BY c DESC
""").fetchall()
print("DUPES =", len(rows))
for r in rows[:50]:
    print(r)
con.close()
