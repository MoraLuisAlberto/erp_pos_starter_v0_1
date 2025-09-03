from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from ..db import SessionLocal

# Usamos el modelo de órdenes para actualizar totales con ORM
try:
    from ..models.pos import PosOrder
except Exception:
    PosOrder = None  # fallback por si el modelo está en otro módulo

router = APIRouter()


def _has_col(rows, name: str) -> bool:
    return any(r[1] == name for r in rows)


class ApplyCouponPayload(BaseModel):
    code: str


@router.get("/coupons/active")
def list_active_coupons():
    s = SessionLocal()
    try:
        cols = s.execute(text("PRAGMA table_info(coupon)")).fetchall()
        has_percent = _has_col(cols, "percent")
        has_value = _has_col(cols, "value")
        rows = s.execute(
            text(
                f"""
            SELECT id, code,
                   {"percent" if has_percent else "0"} as percent,
                   {"value"   if has_value   else "0"} as value,
                   COALESCE(used_count,0) as used_count
            FROM coupon WHERE COALESCE(active,1)=1
        """
            )
        ).fetchall()
        return [
            {
                "id": r[0],
                "code": r[1],
                "percent": float(r[2] or 0),
                "value": float(r[3] or 0),
                "used_count": int(r[4] or 0),
            }
            for r in rows
        ]
    finally:
        s.close()


@router.post("/order/{order_id}/apply-coupon")
def apply_coupon(order_id: int, payload: ApplyCouponPayload):
    s = SessionLocal()
    try:
        if PosOrder is None:
            raise HTTPException(500, "Modelo PosOrder no disponible")
        o = s.get(PosOrder, order_id)
        if not o:
            raise HTTPException(404, "Orden no encontrada")
        if o.status != "draft":
            raise HTTPException(409, f"No se puede aplicar cupón en estado {o.status}")

        # Lee esquema dinámico de coupon
        cols = s.execute(text("PRAGMA table_info(coupon)")).fetchall()
        has_percent = _has_col(cols, "percent")
        has_value = _has_col(cols, "value")

        c = s.execute(
            text(
                f"""
            SELECT id, code,
                   {"percent" if has_percent else "0"} as percent,
                   {"value"   if has_value   else "0"} as value
            FROM coupon
            WHERE code=:c AND COALESCE(active,1)=1
        """
            ),
            {"c": payload.code},
        ).fetchone()
        if not c:
            raise HTTPException(404, "Cupón no existe o no está activo")

        cid, code, percent, value = c[0], c[1], float(c[2] or 0), float(c[3] or 0)

        # Asegura tablas de enlace/auditoría (idempotente)
        s.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS pos_order_coupon (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              order_id INTEGER NOT NULL,
              coupon_id INTEGER NOT NULL
            )
        """
            )
        )
        s.execute(
            text(
                """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_pos_order_coupon
            ON pos_order_coupon(order_id, coupon_id)
        """
            )
        )
        s.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS coupon_audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              coupon_id INTEGER NOT NULL,
              event TEXT NOT NULL,
              notes TEXT NOT NULL
            )
        """
            )
        )

        # Enlace orden↔cupón (idempotente)
        s.execute(
            text(
                """
            INSERT OR IGNORE INTO pos_order_coupon(order_id, coupon_id)
            VALUES (:o,:c)
        """
            ),
            {"o": o.id, "c": cid},
        )

        # Calcula descuento sobre subtotal (o total si no hay subtotal)
        base = float(o.subtotal or o.total or 0.0)
        disc = round(base * percent / 100.0, 2) if percent > 0 else round(value, 2)
        if disc < 0:
            disc = 0.0
        new_total = round(max(base - disc, 0.0), 2)

        # Auditoría de validación (idempotente por (coupon_id,event,notes) único si ya existe)
        notes = f"apply_as={'percent' if percent>0 else 'value'},disc={disc}"
        s.execute(
            text(
                """
            INSERT OR IGNORE INTO coupon_audit(coupon_id,event,notes)
            VALUES (:cid,'validate-ok',:n)
        """
            ),
            {"cid": cid, "n": notes},
        )

        # Actualiza totales en la orden
        o.discount_total = disc
        o.total = new_total
        s.commit()
        s.refresh(o)

        return {
            "order_id": o.id,
            "code": code,
            "discount_applied": disc,
            "subtotal": float(o.subtotal or 0),
            "total": new_total,
            "status": o.status,
        }
    finally:
        s.close()
