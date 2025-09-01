# Minimal para compilar; el original contenia lineas no-Python.
from pydantic import BaseModel
from typing import Optional

class Wallet(BaseModel):
    id: Optional[int] = None
    customer_id: Optional[int] = None
    balance: float = 0.0
