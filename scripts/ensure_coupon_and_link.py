import sys
from sqlalchemy import text
from app.db import SessionLocal

"""
Uso: python scripts/ensure_coupon_and_link.py <ORDER_ID> [CODE]
- Crea cupón CODE (percent 10) si no existe.
- Asegura tablas pos_order_coupon/coupon_audit e índices.
- Inserta link pos_order_coupon(order_id,coupon_id) idempotente.
"""

def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: ensure_coupon_and_link.py <ORDER_ID> [CODE]")
    oid = int(sys.argv[1])
    code = sys.argv[2] if len(sys.argv) > 2 else "WELCOME10"
    s = SessionLocal()
    try:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS coupon (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              code TEXT UNIQUE NOT NULL,
              type TEXT NOT NULL DEFAULT 'percent',
              percent REAL NOT NULL DEFAULT 0,
              used_count INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1
            )
        """))
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_order_coupon (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              order_id INTEGER NOT NULL,
              coupon_id INTEGER NOT NULL
            )
        """))
        s.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_pos_order_coupon ON pos_order_coupon(order_id,coupon_id)"))

        cid = s.execute(text("SELECT id FROM coupon WHERE code=:c"), {"c": code}).scalar()
        if not cid:
            s.execute(text("INSERT INTO coupon(code,type,percent,active) VALUES(:c,'percent',10,1)"), {"c": code})
            cid = s.execute(text("SELECT id FROM coupon WHERE code=:c"), {"c": code}).scalar()

        s.execute(text("""
            INSERT OR IGNORE INTO pos_order_coupon(order_id,coupon_id)
            VALUES (:o,:c)
        """), {"o": oid, "c": cid})

        s.commit()
        print(f"LINKED -> order={oid} coupon={code} (id={cid})")
    finally:
        s.close()

if __name__ == "__main__":
    main()
