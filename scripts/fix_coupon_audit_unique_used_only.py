import os
import sqlite3

from app.db import engine

db = engine.url.database
if not os.path.isabs(db):
    db = os.path.abspath(db)

con = sqlite3.connect(db)
cur = con.cursor()

# 1) Elimina índice amplio previo (si existiera)
cur.execute("DROP INDEX IF EXISTS ux_coupon_audit_used_order")

# 2) Crea índice único parcial SOLO cuando event='used'
cur.execute(
    """
CREATE UNIQUE INDEX IF NOT EXISTS ux_coupon_audit_used_order
ON coupon_audit(coupon_id, notes)
WHERE event='used'
"""
)

con.commit()
con.close()
print("INDEX_USED_ONLY_OK")
