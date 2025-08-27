from sqlalchemy import text
from app.db import SessionLocal

def ensure_wallet_schema():
    s = SessionLocal()
    try:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS wallet(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              customer_id INTEGER NOT NULL UNIQUE,
              balance REAL NOT NULL DEFAULT 0,
              status TEXT DEFAULT 'active',
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS wallet_tx(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              wallet_id INTEGER NOT NULL,
              kind TEXT NOT NULL,
              amount REAL NOT NULL,
              delta REAL NOT NULL,
              sign INTEGER NOT NULL DEFAULT 1,
              reason TEXT,
              order_id INTEGER,
              by_user TEXT DEFAULT 'demo',
              idempotency_key TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        s.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_wallet_tx_key ON wallet_tx(idempotency_key)"))
        s.commit()
        print("WALLET_SCHEMA_OK")
    finally:
        s.close()

if __name__ == "__main__":
    ensure_wallet_schema()
