from app.db import engine, Base
from app.models.customer import Customer  # ensure import
Base.metadata.create_all(bind=engine, checkfirst=True)
print("CUSTOMER_TABLE_OK")
