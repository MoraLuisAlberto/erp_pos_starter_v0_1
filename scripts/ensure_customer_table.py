from app.db import Base, engine

Base.metadata.create_all(bind=engine, checkfirst=True)
print("CUSTOMER_TABLE_OK")
