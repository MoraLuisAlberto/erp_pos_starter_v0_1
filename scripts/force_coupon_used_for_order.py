import sys
from sqlalchemy import text
from app.db import SessionLocal

"""
Idempotente:
- Asegura tablas coupon, coupon_audit, pos_order_coupon e índices.
- Enlaza (INSERT OR IGNORE) WELCOME10 (o el código dado) a la orden.
- Inserta (INSERT OR IGNORE) audit (event='used', notes='order:<order_id>').
- Recalcula used_count del cupón = COUNT(audit.used).
Uso: python scripts/force_coupon_used_for_order.py <ORDER_ID> [COUPON_CODE]
"""

def main():
    if len(sys.argv) < 2:
        print("Usage: force_coupon_used_for_order.py <ORDER_ID> [COUPON_CODE]")
        raise SystemExit(2)
    order_id = int(sys.argv[1])
    code = sys.argv[2] if len(sys.argv) > 2 else "WELCOME10"

    s = SessionLocal()
    try:
        # Esquema mínimo
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
            CREATE TABLE IF NOT EXISTS coupon_audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              coupon_id INTEGER NOT NULL,
              event TEXT NOT NULL,
              notes TEXT NOT NULL
            )
        """))
        # created_at opcional (sin DEFAULT) + backfill
        info = s.execute(text("PRAGMA table_info(coupon_audit)")).fetchall()
        if not any(r[1] == "created_at" for r in info):
            s.execute(text("ALTER TABLE coupon_audit ADD COLUMN created_at TEXT"))
        s.execute(text("UPDATE coupon_audit SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP) WHERE created_at IS NULL"))

        # Índice único de auditoría
        s.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_coupon_audit_evt
            ON coupon_audit(coupon_id, event, notes)
        """))

        # Relación orden↔cupón
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_order_coupon (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              order_id INTEGER NOT NULL,
              coupon_id INTEGER NOT NULL
            )
        """))
        s.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_pos_order_coupon
            ON pos_order_coupon(order_id, coupon_id)
        """))

        # Cupón
        cid = s.execute(text("SELECT id FROM coupon WHERE code=:c"), {"c": code}).scalar()
        if not cid:
            s.execute(text("INSERT INTO coupon(code,type,percent,active) VALUES(:c,'percent',10,1)"), {"c": code})
            cid = s.execute(text("SELECT id FROM coupon WHERE code=:c"), {"c": code}).scalar()

        # Enlace idempotente
        s.execute(text("INSERT OR IGNORE INTO pos_order_coupon(order_id, coupon_id) VALUES (:o, :c)"),
                  {"o": order_id, "c": cid})

        # Auditoría idempotente
        s.execute(text("INSERT OR IGNORE INTO coupon_audit(coupon_id, event, notes) VALUES (:cid, 'used', :n)"),
                  {"cid": cid, "n": f"order:{order_id}"})

        # Recuenta used_count
        cnt = s.execute(text("SELECT COUNT(*) FROM coupon_audit WHERE coupon_id=:cid AND event='used'"),
                        {"cid": cid}).scalar()
        s.execute(text("UPDATE coupon SET used_count=:cnt WHERE id=:cid"), {"cnt": cnt, "cid": cid})

        s.commit()
        print(f"FORCED -> order={order_id} code={code} coupon_id={cid} used_count={cnt}")
    finally:
        s.close()

if __name__ == "__main__":
    main()
