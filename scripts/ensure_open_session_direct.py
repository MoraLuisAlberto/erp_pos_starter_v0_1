import time

from sqlalchemy import text

from app.db import SessionLocal

"""
Abre una sesión 'open' si no existe (idempotente).
Incluye store_id=1, terminal_id=1, user_open_id=1, idem_open único.
"""


def main():
    s = SessionLocal()
    try:
        # Asegura tablas mínimas y registros base
        s.execute(text("CREATE TABLE IF NOT EXISTS pos_store (id INTEGER PRIMARY KEY, name TEXT)"))
        s.execute(
            text(
                "CREATE TABLE IF NOT EXISTS pos_terminal (id INTEGER PRIMARY KEY, store_id INTEGER, name TEXT)"
            )
        )
        s.execute(text("INSERT OR IGNORE INTO pos_store(id,name) VALUES (1,'Main')"))
        s.execute(text("INSERT OR IGNORE INTO pos_terminal(id,store_id,name) VALUES (1,1,'T1')"))

        row = s.execute(
            text("SELECT id FROM pos_session WHERE status='open' ORDER BY id DESC LIMIT 1")
        ).fetchone()
        if row:
            print(f"OPEN_SESSION -> id={row[0]}")
            s.commit()
            return

        idem = f"script-open-{int(time.time())}"
        s.execute(
            text(
                """
            INSERT INTO pos_session(
              store_id, terminal_id, user_open_id, opened_at, status,
              user_close_id, closed_at, idempotency_open, idempotency_close,
              audit_ref, opened_by, closed_by, note,
              expected_cash, counted_pre, counted_final, diff_cash, tolerance,
              idem_open, idem_close
            ) VALUES (
              1, 1, 1, CURRENT_TIMESTAMP, 'open',
              NULL, NULL, :idem, NULL,
              'script', 'script', NULL, NULL,
              0, 0, 0, 0, 0,
              :idem, NULL
            )
        """
            ),
            {"idem": idem},
        )

        row = s.execute(
            text("SELECT id FROM pos_session WHERE status='open' ORDER BY id DESC LIMIT 1")
        ).fetchone()
        print(f"OPEN_SESSION -> id={row[0] if row else ''}")
        s.commit()
    finally:
        s.close()


if __name__ == "__main__":
    main()
