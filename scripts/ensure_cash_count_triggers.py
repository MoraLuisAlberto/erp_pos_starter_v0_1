import os
import sqlite3

from app.db import engine

db_path = engine.url.database
if not os.path.isabs(db_path):
    db_path = os.path.abspath(db_path)

con = sqlite3.connect(db_path)
cur = con.cursor()

cur.executescript(
    """
CREATE TRIGGER IF NOT EXISTS trg_cash_count_stage_default
AFTER INSERT ON cash_count
FOR EACH ROW
WHEN NEW.stage IS NULL
BEGIN
  UPDATE cash_count SET stage = NEW.kind WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_cash_count_created_at_default
AFTER INSERT ON cash_count
FOR EACH ROW
WHEN NEW.created_at IS NULL
BEGIN
  UPDATE cash_count SET created_at = datetime('now') WHERE id = NEW.id;
END;
"""
)

con.commit()
con.close()
print("TRIGGERS_OK")
