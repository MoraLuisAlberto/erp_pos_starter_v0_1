from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, Header, HTTPException
from pydantic import BaseModel, field_validator

# Usamos las mismas utilidades de cupones
from app.routers.pos_coupons import compute_coupon_result, coupon_usage_inc

# Intentamos reutilizar el escritor de auditoría del módulo de cupones.
# Si por alguna razón no existe, definimos un fallback local que escribe al mismo archivo.
try:
    from app.routers.pos_coupons import _audit_write  # type: ignore
except Exception:  # pragma: no cover - fallback defensivo
    import json
    from pathlib import Path

    _AUDIT_FILE = Path("data") / "coupons_audit.jsonl"

    def _audit_write(ev: dict) -> None:
        """Fallback simple: escribe una línea JSONL en el mismo archivo que usa el reporte."""
        _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        if "ts" not in ev:
            ev["ts"] = datetime.utcnow().isoformat()
        with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


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
    customer_id: Optional[int] = None  # requerido si usa cupón


# Idempotencia + auditoría en memoria (demo)
_IDEM: Dict[str, Dict] = {}
_PAY_SEQ = 0
_AUDIT: List[Dict] = []  # entries: {at, coupon_code, customer_id, order_id, payment_id, idem}


@router.post("/pay-discounted")
def pay_discounted(
    payload: PayDiscountedRequest = Body(...),
    x_idem: Optional[str] = Header(default=None, alias="x-idempotency-key"),
):
    """
    Regla importante:
    - Si 'splits' o 'amount' ya traen el total final (descontado), SOLO validamos el cupón,
      NO volvemos a aplicar el descuento sobre ese monto. Así evitamos doble descuento.
    """
    global _PAY_SEQ
    if x_idem and x_idem in _IDEM:
        return _IDEM[x_idem]

    # 1) Determinar total a cobrar (expected_total) a partir de lo que envía el cliente
    #    - Preferimos 'splits' (suma)
    #    - Si no hay, usamos 'amount'
    #    - 'base_total' es opcional y puede representar pre-descuento si el cliente lo desea
    base_total: Optional[Decimal] = None
    if payload.splits:
        base_total = sum([s.amount for s in payload.splits], Decimal("0.00"))
    elif payload.amount is not None:
        base_total = Decimal(str(payload.amount))
    elif payload.base_total is not None:
        base_total = Decimal(str(payload.base_total))
    else:
        raise HTTPException(status_code=422, detail="splits or amount or base_total required")

    expected_total = money(base_total)

    # 2) Si hay cupón: VALIDAMOS pero no reasignamos expected_total
    if payload.coupon_code:
        if payload.customer_id is None:
            raise HTTPException(
                status_code=422, detail="customer_id required when coupon_code is present"
            )
        # Validación (puede leer límites/segmentos, etc.)
        res = compute_coupon_result(payload.coupon_code, expected_total, None, payload.customer_id)
        if not res.get("valid"):
            raise HTTPException(status_code=422, detail=f"invalid_coupon: {res.get('reason')}")

    # 3) Asegurar que splits (si existen) coincidan con el total esperado
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

    # 4) Generar pago
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

    # 5) Consumir uso SOLO en el primer intento (si hay cupón) + auditoría
    if payload.coupon_code:
        if not coupon_usage_inc(payload.coupon_code.strip().upper(), payload.customer_id):
            raise HTTPException(status_code=422, detail="invalid_coupon: usage_limit_reached")

        # Auditoría en memoria (legacy)
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

        # Auditoría persistente (archivo compartido con el reporte)
        try:
            _audit_write(
                {
                    "ts": datetime.utcnow().isoformat(),
                    "kind": "paid",
                    "code": payload.coupon_code.strip().upper(),
                    "customer_id": payload.customer_id,
                    "order_id": payload.order_id,
                    "payment_id": payment_id,
                    "idempotency_key": x_idem,
                }
            )
        except Exception:
            # No rompemos el pago si la auditoría falla.
            pass

    if x_idem:
        _IDEM[x_idem] = resp
    # Exponer cupón en la respuesta (trazabilidad + middleware)
    if "coupon_code" not in resp:
        resp["coupon_code"] = ((payload.coupon_code or getattr(payload, "code", None) or "").strip().upper() or None)
        resp["code"] = resp["coupon_code"]
    return resp
    # Exponer cupón en la respuesta (trazabilidad + middleware)
    resp["coupon_code"] = ((payload.coupon_code or getattr(payload, "code", None) or "").strip().upper() or None)
    resp["code"] = resp["coupon_code"]
