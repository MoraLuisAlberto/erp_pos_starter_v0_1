from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, Header, HTTPException
from pydantic import BaseModel, field_validator

from app.routers.pos_coupons import compute_coupon_result, coupon_usage_inc

router = APIRouter(prefix="/pos/order", tags=["pos", "payx"])


def money(v: Decimal) -> Decimal:
    return (
        v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if isinstance(v, Decimal)
        else Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


class PaySplit(BaseModel):
    method: str
    amount: Decimal

    @field_validator("amount", mode="before")
    @classmethod
    def _to_decimal(cls, v):
        return Decimal(str(v))


class PayDiscountedRequest(BaseModel):
    session_id: int
    order_id: int
    splits: Optional[List[PaySplit]] = None
    method: Optional[str] = None
    amount: Optional[Decimal] = None
    coupon_code: Optional[str] = None
    base_total: Optional[Decimal] = None
    customer_id: Optional[int] = None  # NUEVO (requerido si usa cupón)


# Idempotencia + auditoría en memoria (demo)
_IDEM: Dict[str, Dict] = {}
_PAY_SEQ = 0
_AUDIT: List[Dict] = []  # entries: {at, coupon_code, customer_id, order_id, payment_id, idem}


@router.post("/pay-discounted")
def pay_discounted(
    payload: PayDiscountedRequest = Body(...),
    x_idem: Optional[str] = Header(default=None, alias="x-idempotency-key"),
):
    global _PAY_SEQ
    if x_idem and x_idem in _IDEM:
        return _IDEM[x_idem]

    # Determinar base_total
    base_total: Optional[Decimal] = payload.base_total
    if base_total is None:
        if payload.splits:
            base_total = sum([s.amount for s in payload.splits], Decimal("0.00"))
        elif payload.amount is not None:
            base_total = Decimal(str(payload.amount))
    if base_total is None:
        raise HTTPException(
            status_code=422, detail="base_total/amount/splits required to compute total"
        )

    expected_total = money(base_total)

    # Si hay cupón, revalidar y aplicar límite de uso por cliente
    if payload.coupon_code:
        if payload.customer_id is None:
            raise HTTPException(
                status_code=422, detail="customer_id required when coupon_code is present"
            )
        res = compute_coupon_result(payload.coupon_code, expected_total, None, payload.customer_id)
        if not res["valid"]:
            raise HTTPException(status_code=422, detail=f"invalid_coupon: {res.get('reason')}")
        expected_total = res["new_total"]

    # Asegurar splits = expected_total
    splits = payload.splits
    if not splits:
        if payload.method:
            splits = [PaySplit(method=payload.method, amount=expected_total)]
        else:
            raise HTTPException(status_code=422, detail="splits or method required")
    sum_splits = money(sum([s.amount for s in splits], Decimal("0.00")))
    if sum_splits != expected_total:
        raise HTTPException(
            status_code=422,
            detail=f"splits_total_mismatch: got {sum_splits}, expected {expected_total}",
        )

    # Generar payment
    _PAY_SEQ += 1
    payment_id = _PAY_SEQ

    resp = {
        "order": {
            "order_id": payload.order_id,
            "order_no": f"POS-{payload.order_id:06d}",
            "status": "paid",
            "subtotal": expected_total,
            "discount_total": Decimal("0.00"),
            "tax_total": Decimal("0.00"),
            "total": expected_total,
            "lines": [],
        },
        "payment_id": payment_id,
        "method": splits[0].method if splits else (payload.method or "unknown"),
        "amount": expected_total,
        "splits": [{"method": s.method, "amount": str(money(s.amount))} for s in splits],
    }

    # Consumir uso SOLO en el primer intento (si hay cupón)
    if payload.coupon_code:
        if not coupon_usage_inc(payload.coupon_code.strip().upper(), payload.customer_id):
            # No consumir 2 veces si justo falló consumo.
            raise HTTPException(status_code=422, detail="invalid_coupon: usage_limit_reached")
        _AUDIT.append(
            {
                "at": datetime.utcnow().isoformat(),
                "coupon_code": payload.coupon_code.strip().upper(),
                "customer_id": payload.customer_id,
                "order_id": payload.order_id,
                "payment_id": payment_id,
                "idem": x_idem,
            }
        )

    if x_idem:
        _IDEM[x_idem] = resp
    return resp
