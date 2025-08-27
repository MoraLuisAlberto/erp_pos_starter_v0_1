from sqlalchemy import text
from app.db import SessionLocal
import sys

"""
Recalcula counted_pre / counted_final en pos_session
a partir de cash_count.stage ('pre' / 'final') tomando el último total.
Uso: python scripts/recalc_session_counts.py <SESSION_ID>
"""

def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: recalc_session_counts.py <SESSION_ID>")
    sid = int(sys.argv[1])
    s = SessionLocal()
    try:
        pre = s.execute(text("""
            SELECT total FROM cash_count
            WHERE session_id=:sid AND stage='pre'
            ORDER BY id DESC LIMIT 1
        """), {"sid": sid}).scalar()
        fin = s.execute(text("""
            SELECT total FROM cash_count
            WHERE session_id=:sid AND stage='final'
            ORDER BY id DESC LIMIT 1
        """), {"sid": sid}).scalar()

        pre = float(pre or 0)
        fin = float(fin or 0)

        s.execute(text("""
            UPDATE pos_session
            SET counted_pre=:pre, counted_final=:fin
            WHERE id=:sid
        """), {"pre": pre, "fin": fin, "sid": sid})
        s.commit()
        print(f"RECALC -> session_id={sid} counted_pre={pre} counted_final={fin}")
    finally:
        s.close()

if __name__ == "__main__":
    main()
