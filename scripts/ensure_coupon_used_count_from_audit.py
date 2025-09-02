from sqlalchemy import text

from app.db import SessionLocal


def main():
    s = SessionLocal()
    try:
        s.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS coupon (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              code TEXT UNIQUE NOT NULL,
              type TEXT NOT NULL DEFAULT 'percent',
              percent REAL NOT NULL DEFAULT 0,
              used_count INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1
            )
        """
            )
        )
        s.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS coupon_audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              coupon_id INTEGER NOT NULL,
              event TEXT NOT NULL,
              notes TEXT NOT NULL,
              created_at TEXT
            )
        """
            )
        )
        s.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_coupon_audit_evt ON coupon_audit(coupon_id,event,notes)"
            )
        )
        for cid, code in s.execute(text("SELECT id, code FROM coupon")):
            cnt = s.execute(
                text("SELECT COUNT(*) FROM coupon_audit WHERE coupon_id=:cid AND event='used'"),
                {"cid": cid},
            ).scalar()
            s.execute(
                text("UPDATE coupon SET used_count=:cnt WHERE id=:cid"), {"cnt": cnt, "cid": cid}
            )
            print(f"RECOUNT -> code={code} used_count={cnt}")
        s.commit()
    finally:
        s.close()


if __name__ == "__main__":
    main()
