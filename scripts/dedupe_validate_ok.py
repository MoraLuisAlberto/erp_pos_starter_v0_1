import os, sqlite3
from app.db import engine

db = engine.url.database
if not os.path.isabs(db):
    db = os.path.abspath(db)

con = sqlite3.connect(db)
cur = con.cursor()
cur.execute("""
DELETE FROM coupon_audit
WHERE event='validate-ok'
AND id NOT IN (
    SELECT MIN(id) FROM coupon_audit
    WHERE event='validate-ok'
    GROUP BY coupon_id, event, notes
)
""")
deleted = con.total_changes
con.commit()
con.close()
print(f"VALIDATE_DEDUPE_OK deleted={deleted}")
