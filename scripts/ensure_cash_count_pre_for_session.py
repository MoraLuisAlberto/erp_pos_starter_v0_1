from sqlalchemy import text
from app.db import SessionLocal
import sys

"""
Inserta un cash_count 'pre' para la sesión dada (by_user='demo').
Uso: python scripts/ensure_cash_count_pre_for_session.py <SESSION_ID> <TOTAL>
Idempotente para efecto: puedes correrlo más de una vez; el último total será el visible.
"""

def main():
    if len(sys.argv) < 3:
        raise SystemExit("Usage: ensure_cash_count_pre_for_session.py <SESSION_ID> <TOTAL>")
    sid = int(sys.argv[1]); total = float(sys.argv[2])
    s = SessionLocal()
    try:
        s.execute(text("""
            INSERT INTO cash_count (session_id, stage, created_at, by_user, kind, total, details_json, at)
            VALUES (:sid, 'pre', CURRENT_TIMESTAMP, 'demo', 'pre', :total, '[]', CURRENT_TIMESTAMP)
        """), {"sid": sid, "total": total})
        s.commit()
        row = s.execute(text("SELECT id, stage, kind, total, by_user FROM cash_count WHERE session_id=:sid ORDER BY id DESC LIMIT 1"),
                        {"sid": sid}).fetchone()
        print(f"CASH_PRE_OK id={row[0]} stage={row[1]} kind={row[2]} total={row[3]} by_user={row[4]}")
    finally:
        s.close()

if __name__ == "__main__":
    main()
