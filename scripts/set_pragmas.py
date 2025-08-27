from app.db import engine
with engine.begin() as c:
    c.exec_driver_sql("PRAGMA journal_mode=WAL")
    c.exec_driver_sql("PRAGMA busy_timeout=60000")
print("PRAGMAS_OK")
