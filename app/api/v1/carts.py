from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.schemas import CartIn

router = APIRouter(prefix="/carts", tags=["carts"])


@router.post("/hold", summary="Guardar carrito (hold)")
def hold_cart(payload: CartIn, db: Session = Depends(get_db)):
    return {"ok": True, "status": "HELD"}


@router.post("/resume/{cart_id}", summary="Reanudar carrito")
def resume_cart(cart_id: int, db: Session = Depends(get_db)):
    return {"ok": True, "cart_id": cart_id, "status": "RESUMED"}
