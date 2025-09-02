import os
import sqlite3

from app.db import engine

db = engine.url.database
if not os.path.isabs(db):
    db = os.path.abspath(db)
con = sqlite3.connect(db)
cur = con.cursor()

# Drop triggers antiguos si existieran (idempotente)
try:
    cur.execute("DROP TRIGGER IF EXISTS trg_coupon_on_paid")
except Exception:
    pass

# Crea trigger: al pasar de !=paid a paid, incrementar usos y auditar "applied"
cur.execute(
    """
CREATE TRIGGER trg_coupon_on_paid
AFTER UPDATE OF status ON pos_order
WHEN NEW.status='paid' AND OLD.status!='paid'
BEGIN
  -- incrementar used_count por cada cupón aplicado en la orden
  UPDATE coupon
     SET used_count = COALESCE(used_count,0) + (
         SELECT COUNT(*) FROM pos_order_coupon oc WHERE oc.order_id = NEW.id AND oc.coupon_id = coupon.id
     )
   WHERE id IN (SELECT coupon_id FROM pos_order_coupon WHERE order_id = NEW.id);

  -- auditar aplicación
  INSERT INTO coupon_audit (coupon_id, event, at, by_user, notes)
  SELECT oc.coupon_id, 'applied', datetime('now'), COALESCE(NEW.closed_by, 'system'),
         printf('order_id=%d,value=%.2f', NEW.id, COALESCE(oc.value_applied,0))
    FROM pos_order_coupon oc
   WHERE oc.order_id = NEW.id;
END;
"""
)

con.commit()
con.close()
print("TRIGGER_COUPON_ON_PAID_OK")
