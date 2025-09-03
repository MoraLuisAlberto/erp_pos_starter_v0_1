import os
import sqlite3

from sqlalchemy import Column

from app.db import engine
from app.models.pos_session import CashCount

db_path = engine.url.database
if not os.path.isabs(db_path):
    db_path = os.path.abspath(db_path)


# Mapa muy básico de tipos SQLAlchemy -> SQLite
def to_sqlite_decl(col: Column) -> str:
    t = str(col.type).lower()
    if "integer" in t:
        return f"{col.name} INTEGER"
    if "numeric" in t or "decimal" in t or "float" in t or "real" in t:
        return f"{col.name} NUMERIC"
    if "datetime" in t or "date" in t:
        return f"{col.name} DATETIME"
    if "text" in t:
        return f"{col.name} TEXT"
    # string/varchar
    return f"{col.name} TEXT"


conn = sqlite3.connect(db_path)
cur = conn.cursor()
table = CashCount.__table__
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table.name,))
exists = cur.fetchone() is not None

# Si no existe, créala con SQLAlchemy (crea todo de golpe)
if not exists:
    table.create(bind=engine, checkfirst=True)
    print("ALIGN: table created by ORM")
else:
    # Asegura columnas faltantes (solo ADD COLUMN; SQLite no quita/renombra)
    cur.execute(f"PRAGMA table_info('{table.name}')")
    db_cols = {r[1] for r in cur.fetchall()}  # names
    missing = [c for c in table.columns if c.name not in db_cols]
    for col in missing:
        decl = to_sqlite_decl(col)
        # NOT NULL sin default es delicado; para compatibilidad lo dejamos nullable si la tabla ya existía.
        sql = f"ALTER TABLE {table.name} ADD COLUMN {decl}"
        cur.execute(sql)
        print(f"ALIGN: added column -> {decl}")

conn.commit()
conn.close()
print("ALIGN_OK")
