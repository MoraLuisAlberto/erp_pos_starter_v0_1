import os
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Literal, Optional
from datetime import datetime, timedelta
from .wallet import redeem_in_pos

from ..db import SessionLocal
from ..models.product import PriceListItem
from ..models.pos import PosOrder, PosOrderLine, PosPayment, PosPaymentSplit



# Opcional inventario (no usado en V1)
try:
    from ..models.stock import StockLocation, StockQuant, StockMove  # noqa
except Exception:
    StockLocation = StockQuant = StockMove = None

# Wallet (para redimir en pago)
from .wallet import redeem_in_pos as _wallet_redeem

POLICY = os.getenv("POS_STOCK_POLICY", "bypass")  # bypass | warn | enforce

class DraftItem(BaseModel):
    product_id: int
    qty: float

class DraftOrderRequest(BaseModel):
    session_id: int
    price_list_id: int
    items: list[DraftItem] = Field(..., min_length=1)
    location_code: str = "MAIN"

class PaymentSplit(BaseModel):
    method: Literal["cash","card","wallet"]
    amount: float

class PayRequest(BaseModel):
    order_id: int
    splits: list[PaymentSplit] = Field(..., min_length=1)
    customer_id: Optional[int] = None
    wallet_apply: float = 0.0

class UndoRequest(BaseModel):
    order_id: int

router = APIRouter()

def _serialize_order(o: PosOrder, lines: list[PosOrderLine]):
    return {
        "order_id": o.id, "order_no": o.order_no, "status": o.status,
        "subtotal": float(o.subtotal or 0), "discount_total": float(o.discount_total or 0),
        "tax_total": float(o.tax_total or 0), "total": float(o.total or 0),
        "lines": [{"line_id": l.id, "product_id": l.product_id, "qty": float(l.qty),
                   "unit_price": float(l.unit_price), "line_total": float(l.line_total)} for l in lines]
    }

@router.post("/draft")
def create_order_draft(payload: DraftOrderRequest, x_idempotency_key: str | None = Header(default=None)):
    db: Session = SessionLocal()
    try:
        # Idempotencia (orden)
        if x_idempotency_key:
            dup = db.query(PosOrder).filter_by(idempotency_key=x_idempotency_key).first()
            if dup:
                lines = db.query(PosOrderLine).filter_by(order_id=dup.id).all()
                return _serialize_order(dup, lines)

        subtotal = 0.0
        lines_to_create: list[PosOrderLine] = []

        for it in payload.items:
            pli = db.query(PriceListItem).filter_by(
                price_list_id=payload.price_list_id,
                product_id=it.product_id
            ).first()
            if not pli:
                raise HTTPException(status_code=422, detail=f"Producto {it.product_id} sin precio en lista {payload.price_list_id}")

            # Política de stock (V1 bypass)
            if POLICY in ("warn", "enforce") and StockQuant is not None and StockLocation is not None:
                pass

            line_total = float(pli.price) * float(it.qty)
            subtotal += line_total
            lines_to_create.append(PosOrderLine(product_id=it.product_id, qty=it.qty, unit_price=pli.price, line_total=line_total))

        o = PosOrder(
            session_id=payload.session_id, price_list_id=payload.price_list_id,
            subtotal=subtotal, discount_total=0, tax_total=0, total=subtotal,
            status="draft", undo_until_at=datetime.utcnow() + timedelta(seconds=5),
            idempotency_key=x_idempotency_key
        )
        db.add(o); db.commit(); db.refresh(o)

        o.order_no = f"POS-{o.id:06d}"
        for l in lines_to_create: l.order_id = o.id
        db.add_all(lines_to_create); db.commit()

        lines = db.query(PosOrderLine).filter_by(order_id=o.id).all()
        return _serialize_order(o, lines)
    finally:
        db.close()

@router.post("/pay")
def pay_order(payload: PayRequest, x_idempotency_key: str | None = Header(default=None)):
    db: Session = SessionLocal()
    try:
        o = db.get(PosOrder, payload.order_id)
        if not o: raise HTTPException(404, "Orden no encontrada")

        # Idempotencia de pago (devuelve lo previo)
        if x_idempotency_key:
            dup = db.query(PosPayment).filter_by(idempotency_key=x_idempotency_key, order_id=o.id).first()
            if dup:
                lines = db.query(PosOrderLine).filter_by(order_id=o.id).all()
                splits = db.query(PosPaymentSplit).filter_by(payment_id=dup.id).all()
                return {"order": _serialize_order(o, lines), "payment_id": dup.id, "method": dup.method,
                        "amount": float(dup.amount), "splits": [{"method": s.method, "amount": float(s.amount)} for s in splits]}

        if o.status != "draft":
            if o.status == "paid":
                lines = db.query(PosOrderLine).filter_by(order_id=o.id).all()
                p = db.query(PosPayment).filter_by(order_id=o.id).first()
                sp = db.query(PosPaymentSplit).filter_by(payment_id=p.id).all() if p else []
                return {"order": _serialize_order(o, lines), "payment_id": (p.id if p else None),
                        "method": (p.method if p else None), "amount": (float(p.amount) if p else 0.0),
                        "splits": [{"method": s.method, "amount": float(s.amount)} for s in sp]}
            raise HTTPException(409, f"Orden en estado {o.status}")

        total = float(o.total or 0.0)
        wallet_req = float(payload.wallet_apply or 0.0)
        wallet_req = max(0.0, wallet_req)
        sum_splits = round(sum(float(s.amount) for s in payload.splits), 2)

        if round(wallet_req + sum_splits, 2) != round(total, 2):
            raise HTTPException(422, f"wallet_apply({wallet_req}) + splits({sum_splits}) != total({total})")

        # Si aplica monedero, redime primero (idempotente por header)
        if wallet_req > 1e-9:
            if not payload.customer_id:
                raise HTTPException(422, "Falta customer_id para usar monedero")
            _wallet_redeem(db, payload.customer_id, wallet_req, o.id, x_idempotency_key, by_user="demo")

        method = "mixed" if (len(payload.splits) > 1 or wallet_req > 0) else payload.splits[0].method
        p = PosPayment(order_id=o.id, method=method, amount=total, idempotency_key=x_idempotency_key, by_user="demo")
        db.add(p); db.commit(); db.refresh(p)

        # Guarda splits ingresados
        for s in payload.splits:
            db.add(PosPaymentSplit(payment_id=p.id, method=s.method, amount=s.amount))
        # Añade split de wallet si se usó
        if wallet_req > 1e-9:
            db.add(PosPaymentSplit(payment_id=p.id, method="wallet", amount=wallet_req))
        db.commit()

        o.status = "paid"; db.commit()

        lines = db.query(PosOrderLine).filter_by(order_id=o.id).all()
        sp = db.query(PosPaymentSplit).filter_by(payment_id=p.id).all()
        return {"order": _serialize_order(o, lines), "payment_id": p.id, "method": p.method,
                "amount": float(p.amount), "splits": [{"method": s.method, "amount": float(s.amount)} for s in sp]}
    finally:
        db.close()

@router.post("/undo")
def undo_order(payload: UndoRequest):
    db: Session = SessionLocal()
    try:
        o = db.get(PosOrder, payload.order_id)
        if not o: raise HTTPException(404, "Orden no encontrada")
        now = datetime.utcnow()
        if not o.undo_until_at or now > o.undo_until_at:
            raise HTTPException(409, "Ventana de UNDO expirada")
        if o.status != "draft":
            raise HTTPException(409, f"UNDO soportado en MVP sólo para órdenes 'draft' (actual: {o.status})")

        o.status = "voided"; db.commit()
        lines = db.query(PosOrderLine).filter_by(order_id=o.id).all()
        return {"undone": True, "order": _serialize_order(o, lines)}
    finally:
        db.close()

