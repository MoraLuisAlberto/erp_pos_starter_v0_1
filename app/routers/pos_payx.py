from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional
from pydantic import Field
import json

from fastapi import APIRouter, Body, Header, HTTPException
from pydantic import BaseModel, field_validator, model_validator


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
    coupon_code: Optional[str] = Field(default=None)
    base_total: Optional[Decimal] = None
    customer_id: Optional[int] = None  # requerido si usa cupón
      @model_validator(mode="before")
      @classmethod
      def _unify_coupon_code(cls, v):
          # Acepta {"coupon_code": "..."} o {"code": "..."} y lo guarda en coupon_code
          if isinstance(v, dict):
              code = v.get("coupon_code") or v.get("code")
              if code is not None:
                  v["coupon_code"] = str(code)
          return v




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

    # Idempotencia: si ya vimos este idempotency-key, regresamos la misma respuesta
    if x_idem and x_idem in _IDEM:
        return _IDEM[x_idem]

    # 1) Determinar el total esperado a cobrar
    #    - preferimos `splits` (suma)
    #    - si no hay, usamos `amount`
    #    - opcionalmente capturamos base_total si el cliente ya aplicó el desc.
    from decimal import Decimal
    def D(x):  # helper seguro
        return Decimal(str(x)) if x is not None else Decimal("0")

    expected_total: Decimal
    base_total = None

    if payload.splits:
        expected_total = sum(D(s.amount) for s in payload.splits)
    elif payload.amount is not None:
        expected_total = D(payload.amount)
        base_total = D(payload.base_total if payload.base_total is not None else payload.amount)
    else:
        raise HTTPException(status_code=400, detail="missing_total: amount or splits")

    # Si no hay splits, construimos uno “cash” con el total
    splits = payload.splits or [PaySplit(method="cash", amount=expected_total)]


    # 2) Validación/consumo de cupón SOLO si el cliente envió cupón.
    #    Si el cliente ya envió el total final, NO volvemos a descontar (evita doble descuento).
    if payload.coupon_code:
        ok = coupon_usage_inc(payload.coupon_code.strip().upper(), payload.customer_id)
        if not ok:
            raise HTTPException(status_code=422, detail="invalid_coupon: usage_limit_reached")

    # 3) Generar respuesta “paid”
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

      # Exponer cupón en la respuesta (trazabilidad + middleware)
      resp["coupon_code"] = ((payload.coupon_code or "").strip().upper() or None)
      resp["code"] = resp["coupon_code"]


    # 4) Auditorías
    _AUDIT.append({
        "at": datetime.utcnow().isoformat(),
        "coupon_code": (payload.coupon_code or "").strip().upper() or None,
        "customer_id": payload.customer_id,
        "order_id": payload.order_id,
        "payment_id": payment_id,
        "idem": x_idem,
    })

    try:
        _audit_write({
            "ts": datetime.utcnow().isoformat(),
            "kind": "paid",
            "code": (payload.coupon_code or "").strip().upper() or None,
            "customer_id": payload.customer_id,
            "order_id": payload.order_id,
            "payment_id": payment_id,
            "idempotency_key": x_idem,
            "base_total": base_total if base_total is not None else expected_total,
            "paid_total": expected_total,
            "path": "/pos/order/pay-discounted",
            "method": payload.method or "cash",
        })
    except Exception:
        # no rompemos el pago si falla la auditoría
        pass

    # 5) Cache idempotente
    if x_idem:
        _IDEM[x_idem] = resp

    return resp

