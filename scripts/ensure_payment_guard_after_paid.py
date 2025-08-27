import os, sqlite3
from app.db import engine

db_path = engine.url.database
if not os.path.isabs(db_path):
    db_path = os.path.abspath(db_path)

con = sqlite3.connect(db_path)
cur = con.cursor()

cur.executescript("""
CREATE TRIGGER IF NOT EXISTS trg_pos_payment_block_after_paid
BEFORE INSERT ON pos_payment
FOR EACH ROW
WHEN (SELECT status FROM pos_order WHERE id = NEW.order_id) = 'paid'
BEGIN
  SELECT RAISE(ABORT, 'ORDER_ALREADY_PAID');
END;
""")

con.commit()
con.close()
print("PAYMENT_GUARD_OK table=pos_payment")
