import sqlite3, os
from app.db import engine

db = engine.url.database
if not os.path.isabs(db): db = os.path.abspath(db)
con = sqlite3.connect(db); cur = con.cursor()
cur.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS ux_coupon_audit_used_order
ON coupon_audit(coupon_id, event, notes)
""")
con.commit(); con.close()
print("COUPON_AUDIT_UNIQUE_OK")
