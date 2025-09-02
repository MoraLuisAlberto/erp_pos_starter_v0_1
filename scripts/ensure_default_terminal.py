from sqlalchemy import text

from app.db import SessionLocal


def table_exists(s, t):
    return bool(
        s.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"), {"t": t}
        ).fetchone()
    )


def main():
    s = SessionLocal()
    try:
        # si existen, asegura id=1
        if table_exists(s, "pos_store"):
            s.execute(text("INSERT OR IGNORE INTO pos_store(id,name) VALUES (1,'Main')"))
        if table_exists(s, "pos_terminal"):
            # intenta con store_id=1 si existe pos_store
            has_store = table_exists(s, "pos_store")
            if has_store:
                s.execute(
                    text("INSERT OR IGNORE INTO pos_terminal(id,store_id,name) VALUES (1,1,'T1')")
                )
            else:
                # sin pos_store, inserta columnas básicas
                try:
                    s.execute(text("INSERT OR IGNORE INTO pos_terminal(id,name) VALUES (1,'T1')"))
                except Exception:
                    pass
        s.commit()
        # imprime estado mínimo
        try:
            row = s.execute(text("SELECT id,name FROM pos_store WHERE id=1")).fetchone()
            (
                print(f"STORE -> id={row[0]} name={row[1]}")
                if row
                else print("STORE -> (no table or no row)")
            )
        except Exception:
            print("STORE -> (no table)")
        try:
            row = s.execute(text("SELECT id FROM pos_terminal WHERE id=1")).fetchone()
            print(f"TERMINAL -> id={row[0]}") if row else print("TERMINAL -> (no table or no row)")
        except Exception:
            print("TERMINAL -> (no table)")
    finally:
        s.close()


if __name__ == "__main__":
    main()
