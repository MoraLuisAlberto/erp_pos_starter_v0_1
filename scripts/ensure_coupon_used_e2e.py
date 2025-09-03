import sys

from sqlalchemy import text

from app.db import SessionLocal

if len(sys.argv) < 2:
    raise SystemExit("Usage: ensure_coupon_used_e2e.py <ORDER_ID>")
oid = int(sys.argv[1])
s = SessionLocal()
try:
    rows = s.execute(
        text(
            """
        SELECT c.id FROM coupon c
        JOIN pos_order_coupon poc ON poc.coupon_id=c.id
        WHERE poc.order_id=:oid
    """
        ),
        {"oid": oid},
    ).fetchall()
    for (cid,) in rows:
        s.execute(
            text(
                "INSERT OR IGNORE INTO coupon_audit(coupon_id,event,notes) VALUES (:cid,'used',:n)"
            ),
            {"cid": cid, "n": f"order:{oid}"},
        )
    s.commit()
    print(f"ENSURE_AUDIT_FOR_ORDER {oid} rows={len(rows)}")
finally:
    s.close()
