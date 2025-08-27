from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db import SessionLocal

def column_exists(s, table, col):
    return any(r[1]==col for r in s.execute(text(f"PRAGMA table_info({table})")).fetchall())

def index_exists(s, name):
    return bool(s.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND name=:n"), {"n":name}).fetchone())

def trigger_exists(s, name):
    return bool(s.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND name=:n"), {"n":name}).fetchone())

def _dedup(s):
    removed = 0
    dups = s.execute(text("""
        SELECT coupon_id, event, notes, COUNT(*) AS cnt
        FROM coupon_audit
        GROUP BY coupon_id, event, notes
        HAVING COUNT(*) > 1
    """)).fetchall()
    for cid, ev, nt, cnt in dups:
        keep = s.execute(text("""
            SELECT id FROM coupon_audit
            WHERE coupon_id=:cid AND event=:ev AND notes=:nt
            ORDER BY id
        """), {"cid":cid,"ev":ev,"nt":nt}).fetchall()[0][0]
        s.execute(text("""
            DELETE FROM coupon_audit
            WHERE coupon_id=:cid AND event=:ev AND notes=:nt AND id<>:keep
        """), {"cid":cid,"ev":ev,"nt":nt,"keep":keep})
        removed += (cnt-1)
    return removed

def main():
    s = SessionLocal()
    try:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS coupon_audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              coupon_id INTEGER NOT NULL,
              event TEXT NOT NULL,
              notes TEXT NOT NULL
            )
        """))
        added_created = False
        if not column_exists(s,"coupon_audit","created_at"):
            # Sin DEFAULT (constante no permitida); luego backfill y trigger
            s.execute(text("ALTER TABLE coupon_audit ADD COLUMN created_at TEXT"))
            added_created = True
        # Backfill created_at nulos
        s.execute(text("UPDATE coupon_audit SET created_at=COALESCE(created_at, CURRENT_TIMESTAMP) WHERE created_at IS NULL"))
        # Trigger para setear created_at en futuros inserts
        if not trigger_exists(s,"trg_coupon_audit_created_at"):
            s.execute(text("""
                CREATE TRIGGER trg_coupon_audit_created_at
                AFTER INSERT ON coupon_audit
                FOR EACH ROW
                WHEN NEW.created_at IS NULL
                BEGIN
                  UPDATE coupon_audit SET created_at=CURRENT_TIMESTAMP WHERE id=NEW.id;
                END;
            """))
        removed = _dedup(s)
        if not index_exists(s,"ux_coupon_audit_evt"):
            try:
                s.execute(text("CREATE UNIQUE INDEX ux_coupon_audit_evt ON coupon_audit(coupon_id,event,notes)"))
            except SQLAlchemyError:
                removed += _dedup(s)
                s.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_coupon_audit_evt ON coupon_audit(coupon_id,event,notes)"))
        s.commit()
        print(f"SCHEMA_OK created_at={'ADDED' if added_created else 'EXISTING'} dups_removed={removed}")
    finally:
        s.close()

if __name__ == "__main__":
    main()
