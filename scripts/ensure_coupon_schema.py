from sqlalchemy import text

from app.db import SessionLocal

REQ_COLS = {
    "type": "TEXT",
    "percent": "REAL",
    "used_count": "INTEGER",
    "active": "INTEGER",
    # NOTA: no forzamos crear "value"; si ya existe y es NOT NULL, lo rellenamos al insertar
}


def table_exists(s, name):
    return bool(
        s.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"), {"n": name}
        ).fetchone()
    )


def col_info(s, table):
    # [(cid, name, type, notnull, dflt_value, pk)]
    return s.execute(text(f"PRAGMA table_info({table})")).fetchall()


def col_names(s, table):
    return [r[1] for r in col_info(s, table)]


def ensure_table_coupon(s):
    if not table_exists(s, "coupon"):
        s.execute(
            text(
                """
            CREATE TABLE coupon(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              code TEXT UNIQUE NOT NULL
            )
        """
            )
        )
    existing = set(col_names(s, "coupon"))
    for col, sqltype in REQ_COLS.items():
        if col not in existing:
            default = "0" if sqltype in ("INTEGER", "REAL") else "''"
            s.execute(text(f"ALTER TABLE coupon ADD COLUMN {col} {sqltype} DEFAULT {default}"))
    s.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_coupon_code ON coupon(code)"))
    s.commit()


def ensure_coupon_audit(s):
    if not table_exists(s, "coupon_audit"):
        s.execute(
            text(
                """
            CREATE TABLE coupon_audit(
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
    s.commit()


def ensure_pos_order_coupon(s):
    if not table_exists(s, "pos_order_coupon"):
        s.execute(
            text(
                """
            CREATE TABLE pos_order_coupon(
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
    s.commit()


def safe_default(col_type):
    ctype = (col_type or "").lower()
    if any(k in ctype for k in ("int", "real", "floa", "doub", "num", "dec")):
        return 0 if "int" in ctype else 0.0
    return ""  # TEXT u otros


def seed_welcome10(s):
    row = s.execute(text("SELECT id FROM coupon WHERE code='WELCOME10'")).fetchone()
    if row:
        return

    # Construye el INSERT dinámico respetando NOT NULL sin default
    info = col_info(s, "coupon")
    data = {"code": "WELCOME10"}
    # defaults “estándar”:
    if "type" in [c[1] for c in info]:
        data["type"] = "percent"
    if "percent" in [c[1] for c in info]:
        data["percent"] = 10
    if "used_count" in [c[1] for c in info]:
        data["used_count"] = 0
    if "active" in [c[1] for c in info]:
        data["active"] = 1

    # Rellena cualquier NOT NULL sin default que siga faltando (p.ej. value)
    names_in_data = set(data.keys()) | {"id"}
    for cid, name, ctype, notnull, dflt, pk in info:
        if notnull == 1 and pk == 0 and dflt is None and name not in names_in_data:
            data[name] = safe_default(ctype)

    cols = ",".join(data.keys())
    params = ",".join(f":{k}" for k in data.keys())
    s.execute(text(f"INSERT INTO coupon({cols}) VALUES ({params})"), data)
    s.commit()


def recalc_used_count(s):
    if table_exists(s, "coupon_audit"):
        s.execute(
            text(
                """
            UPDATE coupon
            SET used_count = IFNULL((
                SELECT COUNT(*) FROM coupon_audit a
                WHERE a.coupon_id = coupon.id AND a.event='used'
            ), 0)
        """
            )
        )
        s.commit()


def main():
    s = SessionLocal()
    try:
        ensure_table_coupon(s)
        ensure_coupon_audit(s)
        ensure_pos_order_coupon(s)
        seed_welcome10(s)
        recalc_used_count(s)
        print("SCHEMA_COUPON_OK")
    finally:
        s.close()


if __name__ == "__main__":
    main()
