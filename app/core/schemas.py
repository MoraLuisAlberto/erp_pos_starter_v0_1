from pydantic import BaseModel, Field
from typing import List, Optional

class ScanLine(BaseModel):
    code: str
    qty: float = 1
    price: float
    discount: float = 0.0

class SaleCreate(BaseModel):
    store_id: int
    user_id: int
    cash_session_id: int
    customer_id: Optional[int] = None
    lines: List[ScanLine] = Field(default_factory=list)
    coupon_code: Optional[str] = None

class PaymentIn(BaseModel):
    sale_id: int
    method: str
    amount: float
    bank: Optional[str] = None
    card_last4: Optional[str] = None
    ext_ref: Optional[str] = None

class CartIn(BaseModel):
    store_id: int
    user_id: int
    payload: dict

class CouponCheck(BaseModel):
    code: str
    sale_total: float
    customer_segment: Optional[str] = None
