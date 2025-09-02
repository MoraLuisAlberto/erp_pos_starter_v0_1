import json
import os
import sqlite3

from app.db import engine

db = engine.url.database
if not os.path.isabs(db):
    db = os.path.abspath(db)

order_id = int(os.environ.get("ORDER_ID", "0") or "0")

con = sqlite3.connect(db)
cur = con.cursor()
rows = cur.execute(
    """
  SELECT id, order_id, method, amount, idempotency_key, captured_at
  FROM pos_payment
  WHERE order_id=?
  ORDER BY id
""",
    (order_id,),
).fetchall()
con.close()

print(
    json.dumps({"order_id": order_id, "count": len(rows), "payments": rows}, default=str, indent=2)
)
