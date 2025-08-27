import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# Base para modelos (lo importa app.main)
Base = declarative_base()

# Ruta absoluta al erp.db (raíz del proyecto)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DB_FILE = os.path.join(BASE_DIR, "erp.db")
ABS_URL = "sqlite:///" + DB_FILE.replace("\\", "/")

# Permite override por variable de entorno
SQLALCHEMY_DATABASE_URL = os.getenv("DB_URL", ABS_URL)

# Engine con timeout alto (contención ligera)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 60},
    pool_pre_ping=True,
)

# PRAGMAs por conexión
@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA busy_timeout=60000;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.execute("PRAGMA synchronous=NORMAL;")
    finally:
        cur.close()

# Forzar WAL una vez (persistente en el archivo)
with engine.connect() as conn:
    conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
    conn.exec_driver_sql("PRAGMA foreign_keys=ON;")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependencia FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
