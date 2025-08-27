from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os, sqlite3, datetime

from app.routers.coupon import validate_coupon, ValidateBody  # reutilizamos la validación oficial

router = APIRouter()

class ApplyCouponsBody(BaseModel):
    order_id: int
    coupons: List[str]           # MVP: tomamos el primero válido
    customer_id: Optional[int] = None

def _db_path():
    from app.db import engine
    p = engine.url.database
    if not os.path.isabs(p): p = os.path.abspath(p)
    return p

def _fetch_order(con: sqlite3.Connection, order_id: int) -> Optional[Dict[str, Any]]:
    row = con.execute("""SELECT id, subtotal, discount_total, tax_total, total, status
                         FROM pos_order WHERE id=?""", (order_id,)).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "subtotal": float(row[1] or 0), "discount_total": float(row[2] or 0),
        "tax_total": float(row[3] or 0), "total": float(row[4] or 0), "status": row[5]
    }

def _recalc_subtotal(con: sqlite3.Connection, order_id: int) -> float:
    row = con.execute("""SELECT COALESCE(SUM(line_total),0) FROM pos_order_line WHERE order_id=?""", (order_id,)).fetchone()
    return float(row[0] or 0)

@router.post("/apply-coupons")
def apply_coupons(body: ApplyCouponsBody):
    if not body.coupons:
        raise HTTPException(status_code=400, detail="COUPONS_REQUIRED")

    dbp = _db_path()
    con = sqlite3.connect(dbp)
    try:
        # 1) Orden y estado
        od = _fetch_order(con, body.order_id)
        if not od:
            raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")
        if od["status"] != "draft":
            raise HTTPException(status_code=400, detail="ONLY_DRAFT_ACCEPTS_COUPONS")

        # 2) Recalcular subtotal por si cambió el carrito
        subtotal = _recalc_subtotal(con, body.order_id)

        # 3) Intentar validar el primer cupón que pase
        chosen = None
        for code in body.coupons:
            code = (code or "").strip()
            if not code:
                continue
            # reutiliza el validador oficial
            res = validate_coupon(
                ValidateBody(code=code, order_subtotal=subtotal, customer_id=body.customer_id),
                x_user="demo"   # auditoría quedará como "demo" (luego lo ligamos a user real)
            )
            if res and res.get("valid"):
                chosen = res
                break

        # 4) Si ninguno válido:
        if not chosen:
            raise HTTPException(status_code=400, detail="NO_VALID_COUPON")

        discount = float(chosen.get("discount") or 0)
        discount = round(discount, 2)

        # 5) Persistir: limpiar cupones previos de esa orden (MVP: un cupón)
        con.execute("DELETE FROM pos_order_coupon WHERE order_id=?", (body.order_id,))

        # Buscar id real del cupón por code
        rowc = con.execute("SELECT id FROM coupon WHERE UPPER(code)=UPPER(?)", (chosen["code"],)).fetchone()
        coupon_id = rowc[0] if rowc else None

        con.execute("""INSERT INTO pos_order_coupon (order_id, coupon_id, code_snapshot, value_applied)
                       VALUES (?,?,?,?)""",
                    (body.order_id, coupon_id, chosen["code"], discount))

        # 6) Actualizar totales en la orden
        new_discount_total = discount
        new_total = round(subtotal - new_discount_total, 2)

        con.execute("""UPDATE pos_order
                          SET subtotal=?, discount_total=?, total=?
                        WHERE id=?""",
                    (subtotal, new_discount_total, new_total, body.order_id))
        con.commit()

        # 7) Responder orden + líneas + cupones
        lines = con.execute("""SELECT id, product_id, qty, unit_price, discount, line_total
                               FROM pos_order_line WHERE order_id=?""", (body.order_id,)).fetchall()
        coupons = con.execute("""SELECT id, order_id, coupon_id, code_snapshot, value_applied
                                 FROM pos_order_coupon WHERE order_id=?""", (body.order_id,)).fetchall()

        return {
            "order": {
                "order_id": body.order_id,
                "status": "draft",
                "subtotal": subtotal,
                "discount_total": new_discount_total,
                "tax_total": 0.0,
                "total": new_total,
                "lines": [
                    {"line_id": r[0], "product_id": r[1], "qty": float(r[2] or 0),
                     "unit_price": float(r[3] or 0), "discount": float(r[4] or 0),
                     "line_total": float(r[5] or 0)} for r in lines
                ],
                "coupons": [
                    {"id": r[0], "order_id": r[1], "coupon_id": r[2],
                     "code": r[3], "value_applied": float(r[4] or 0)} for r in coupons
                ]
            }
        }
    finally:
        con.close()
