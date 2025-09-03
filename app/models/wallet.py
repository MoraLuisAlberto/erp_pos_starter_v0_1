# Minimal para compilar; el original contenia lineas no-Python.
from typing import Optional

from pydantic import BaseModel


class Wallet(BaseModel):
    id: Optional[int] = None
    customer_id: Optional[int] = None
    balance: float = 0.0
