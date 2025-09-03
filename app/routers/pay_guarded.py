from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db

# Opcional: si existe el servicio de cupones, lo usamos; si no, seguimos sin fallo.
try:
    from ..services.coupon_usage import mark_coupons_used
except Exception:  # pragma: no cover

    def mark_coupons_used(db, order_id: int, by_user: str = "pos"):
        return None


router = APIRouter()


class Split(BaseModel):
    method: str
    amount: float


class PayBody(BaseModel):
    order_id: int
    splits: List[Split]


def _load_order_payload(db: Session, order_id: int) -> Dict:
    # order
    o = db.execute(
        text(
            """
        SELECT id, order_no, status, subtotal, discount_total, tax_total, total
        FROM pos_order WHERE id = :oid
    """
        ),
        {"oid": order_id},
    ).fetchone()
    if not o:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    # lines
    lines = db.execute(
        text(
            """
        SELECT id, product_id, qty, unit_price, line_total
        FROM pos_order_line WHERE order_id = :oid
        ORDER BY id
    """
        ),
        {"oid": order_id},
    ).fetchall()
    return {
        "order_id": o.id,
        "order_no": o.order_no,
        "status": o.status,
        "subtotal": float(o.subtotal or 0),
        "discount_total": float(o.discount_total or 0),
        "tax_total": float(o.tax_total or 0),
        "total": float(o.total or 0),
        "lines": [
            {
                "line_id": r.id,
                "product_id": r.product_id,
                "qty": float(r.qty or 0),
                "unit_price": float(r.unit_price or 0),
                "line_total": float(r.line_total or 0),
            }
            for r in lines
        ],
    }


def _load_payment_by_key(db: Session, idem_key: str):
    if not idem_key:
        return None
    row = db.execute(
        text(
            """
        SELECT id, order_id, method, amount
        FROM pos_payment
        WHERE idempotency_key = :k
        ORDER BY id DESC
        LIMIT 1
    """
        ),
        {"k": idem_key},
    ).fetchone()
    return row


@router.post("/pay-guarded")
def pay_guarded(
    body: PayBody,
    x_idem: Optional[str] = Header(
        default=None, alias="X-Idempotency-Key", convert_underscores=False
    ),
    db: Session = Depends(get_db),
):
    # 1) Reproducción idempotente por key (replay SIEMPRE que exista)
    prev = _load_payment_by_key(db, x_idem or "")
    if prev:
        order_payload = _load_order_payload(db, prev.order_id)
        return {
            "order": order_payload,
            "payment_id": prev.id,
            "method": prev.method,
            "amount": float(prev.amount or 0),
            "splits": [s.model_dump() for s in body.splits],  # eco del request
        }

    # 2) Orden y estado
    o = db.execute(
        text(
            """
        SELECT id, status, total FROM pos_order WHERE id = :oid
    """
        ),
        {"oid": body.order_id},
    ).fetchone()
    if not o:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    if (o.status or "").lower() == "paid":
        # No hay pago registrado con esta key, pero la orden ya está pagada: bloquear
        raise HTTPException(status_code=409, detail="ORDER_ALREADY_PAID")

    # 3) Insertar pago y splits
    total = float(o.total or 0)
    captured_at = db.execute(text("SELECT datetime('now')")).scalar()
    db.execute(
        text(
            """
        INSERT INTO pos_payment (order_id, method, amount, captured_at, idempotency_key, ref_ext, by_user)
        VALUES (:oid, :m, :a, :at, :k, NULL, 'demo')
    """
        ),
        {
            "oid": body.order_id,
            "m": body.splits[0].method if body.splits else "cash",
            "a": total,
            "at": captured_at,
            "k": x_idem or None,
        },
    )
    # id del pago recién insertado
    pay_id = db.execute(text("SELECT last_insert_rowid()")).scalar()

    # splits
    for s in body.splits:
        db.execute(
            text(
                """
            INSERT INTO pos_payment_split (payment_id, method, amount)
            VALUES (:pid, :m, :a)
        """
            ),
            {"pid": pay_id, "m": s.method, "a": float(s.amount or 0)},
        )

    # 4) Marcar orden como pagada
    db.execute(text("UPDATE pos_order SET status='paid' WHERE id = :oid"), {"oid": body.order_id})

    # 5) Marcar cupones como usados (idempotente)
    mark_coupons_used(db, body.order_id, by_user="pos")

    db.commit()

    # 6) Respuesta
    order_payload = _load_order_payload(db, body.order_id)
    return {
        "order": order_payload,
        "payment_id": pay_id,
        "method": body.splits[0].method if body.splits else "cash",
        "amount": total,
        "splits": [s.model_dump() for s in body.splits],
    }
