import os, sqlite3, shutil
from app.db import engine

db_path = engine.url.database
if not os.path.isabs(db_path):
    db_path = os.path.abspath(db_path)

# Backup antes de tocar nada
bak = db_path + ".bak_cashcount_mig"
if os.path.exists(db_path):
    shutil.copy2(db_path, bak)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("PRAGMA foreign_keys=off")
conn.execute("BEGIN")

# Lee esquema actual de cash_count si existe
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cash_count'")
exists = cur.fetchone() is not None

if exists:
    # Recrea tabla con stage NULL (sin NOT NULL)
    cur.execute("""
        CREATE TABLE cash_count__new(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            stage VARCHAR NULL,
            created_at DATETIME NULL,
            by_user VARCHAR(60) NULL,
            kind VARCHAR(10) NOT NULL,
            total NUMERIC(12,2) DEFAULT 0,
            details_json TEXT NULL,
            at DATETIME NULL
        )
    """)
    # Copia datos desde la vieja (mapeando columnas si faltan)
    # Nota: usamos COALESCE para stage por si había valores previos
    cur.execute("""
        INSERT INTO cash_count__new (id, session_id, stage, created_at, by_user, kind, total, details_json, at)
        SELECT
            id,
            session_id,
            COALESCE(stage, kind),
            created_at,
            by_user,
            COALESCE(kind, 'final'),
            COALESCE(total, 0),
            details_json,
            at
        FROM cash_count
    """)
    cur.execute("DROP TABLE cash_count")
    cur.execute("ALTER TABLE cash_count__new RENAME TO cash_count")
else:
    # Si no existía, créala directamente con stage NULL
    cur.execute("""
        CREATE TABLE cash_count(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            stage VARCHAR NULL,
            created_at DATETIME NULL,
            by_user VARCHAR(60) NULL,
            kind VARCHAR(10) NOT NULL,
            total NUMERIC(12,2) DEFAULT 0,
            details_json TEXT NULL,
            at DATETIME NULL
        )
    """)

conn.commit()
cur.execute("PRAGMA foreign_keys=on")
conn.close()
print("MIG_CASH_COUNT_OK")
