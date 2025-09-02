import os
import sqlite3

from app.db import engine

db = engine.url.database
if not os.path.isabs(db):
    db = os.path.abspath(db)

con = sqlite3.connect(db)
cur = con.cursor()

rows = cur.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'").fetchall()
to_drop = []
for n, sql in rows:
    s = (sql or "").lower()
    # Triggers con columnas que ya no existen
    if "closed_by" in s or "closed_at" in s:
        to_drop.append(n)
    # Triggers legacy que hacen UPDATE/INSERT sobre pos_order con NEW./OLD. mal definidos
    if "pos_order" in s and "new." in s:
        # Mantén el trigger sano que está en pos_payment (idempotente / ORDER_ALREADY_PAID)
        if "after insert on pos_payment" in s:
            continue
        to_drop.append(n)

dropped = 0
for n in set(to_drop):
    cur.execute(f"DROP TRIGGER IF EXISTS {n}")
    dropped += 1

con.commit()
print("DROPPED", dropped)
con.close()
