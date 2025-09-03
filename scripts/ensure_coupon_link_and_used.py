import sys

from sqlalchemy import text

from app.db import SessionLocal


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: ensure_coupon_link_and_used.py <ORDER_ID> [COUPON_CODE]")
    oid = int(sys.argv[1])
    code = sys.argv[2] if len(sys.argv) > 2 else "WELCOME10"

    s = SessionLocal()
    try:
        # 1) Asegura existencia de cupón (si no existe, lo crea como percent 10 activo)
        cid = s.execute(text("SELECT id FROM coupon WHERE code=:c"), {"c": code}).scalar()
        if not cid:
            # Inserción robusta (respeta columnas existentes)
            # Lee columnas de coupon
            cols = s.execute(text("PRAGMA table_info(coupon)")).fetchall()
            names = {c[1] for c in cols}
            data = {"code": code}
            if "type" in names:
                data["type"] = "percent"
            if "percent" in names:
                data["percent"] = 10
            if "used_count" in names:
                data["used_count"] = 0
            if "active" in names:
                data["active"] = 1
            # Rellena NOT NULL sin default que falten
            for _, name, ctype, notnull, dflt, pk in cols:
                if notnull == 1 and pk == 0 and dflt is None and name not in data and name != "id":
                    ctype = (ctype or "").lower()
                    if "int" in ctype:
                        data[name] = 0
                    elif any(k in ctype for k in ("real", "floa", "doub", "num", "dec")):
                        data[name] = 0.0
                    else:
                        data[name] = ""
            cols_ins = ",".join(data.keys())
            params = ",".join(f":{k}" for k in data.keys())
            s.execute(text(f"INSERT INTO coupon({cols_ins}) VALUES ({params})"), data)
            s.commit()
            cid = s.execute(text("SELECT id FROM coupon WHERE code=:c"), {"c": code}).scalar()

        # 2) Enlaza orden↔cupón
        s.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS pos_order_coupon(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              order_id INTEGER NOT NULL,
              coupon_id INTEGER NOT NULL
            )
        """
            )
        )
        s.execute(
            text(
                """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_pos_order_coupon
            ON pos_order_coupon(order_id, coupon_id)
        """
            )
        )
        s.execute(
            text("INSERT OR IGNORE INTO pos_order_coupon(order_id, coupon_id) VALUES (:o,:c)"),
            {"o": oid, "c": cid},
        )

        # 3) Auditoría used (idempotente)
        s.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS coupon_audit(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              coupon_id INTEGER NOT NULL,
              event TEXT NOT NULL,
              notes TEXT NOT NULL
            )
        """
            )
        )
        s.execute(
            text(
                """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_coupon_audit_evt
            ON coupon_audit(coupon_id, event, notes)
        """
            )
        )
        s.execute(
            text("INSERT OR IGNORE INTO coupon_audit(coupon_id,event,notes) VALUES (:c,'used',:n)"),
            {"c": cid, "n": f"order:{oid}"},
        )

        # 4) Recalcula used_count SOLO de este cupón
        s.execute(
            text(
                """
            UPDATE coupon
            SET used_count = IFNULL((
                SELECT COUNT(*) FROM coupon_audit a
                WHERE a.coupon_id = coupon.id AND a.event='used'
            ), 0)
            WHERE id=:cid
        """
            ),
            {"cid": cid},
        )
        s.commit()

        # 5) Reporte
        used = s.execute(text("SELECT used_count FROM coupon WHERE id=:cid"), {"cid": cid}).scalar()
        print(f"LINKED code={code} order={oid} coupon_id={cid} used_count={used}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
