from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/pos", tags=["pos-min"])

# Estado en memoria para el MVP
_orders: Dict[int, Dict[str, Any]] = {}
_next_id = 1


class Item(BaseModel):
    product_id: int
    qty: float = Field(gt=0)
    unit_price: float
    price: Optional[float] = None


class DraftIn(BaseModel):
    customer_id: Optional[int] = None
    session_id: int
    price_list_id: Optional[int] = None
    items: List[Item]


@router.post("/order/draft")
def draft_order(body: DraftIn):
    global _next_id
    total = 0.0
    lines = []
    for it in body.items:
        unit = it.price if it.price is not None else it.unit_price
        lt = float(unit) * float(it.qty)
        total += lt
        lines.append(
            {
                "line_id": _next_id,
                "product_id": it.product_id,
                "qty": float(it.qty),
                "unit_price": float(unit),
                "line_total": float(lt),
            }
        )
    oid = _next_id
    _next_id += 1
    order = {
        "order_id": oid,
        "order_no": f"POS-{oid:06d}",
        "status": "draft",
        "subtotal": float(total),
        "discount_total": 0.0,
        "tax_total": 0.0,
        "total": float(total),
        "lines": lines,
    }
    _orders[oid] = order
    return order


@router.post("/order/undo")
def undo_order(order_id: int, session_id: int, reason: Optional[str] = None):
    o = _orders.get(order_id)
    if not o:
        return {"undone": False, "reason": "order_not_found"}
    if o["status"] == "draft":
        o["status"] = "voided"
        return {"undone": True, "order": o}
    return {"undone": False, "reason": f"only_draft_supported (actual: {o['status']})"}
