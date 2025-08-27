import os, sqlite3
from app.db import engine

db_path = engine.url.database
if not os.path.isabs(db_path):
    db_path = os.path.abspath(db_path)

con = sqlite3.connect(db_path)
cur = con.cursor()

cur.executescript("""
CREATE UNIQUE INDEX IF NOT EXISTS ux_pos_payment_order_id_idem
ON pos_payment(order_id, idempotency_key);
""")

con.commit()
con.close()
print("PAYMENT_IDEMPOTENCY_INDEX_OK")
