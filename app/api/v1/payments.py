from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.schemas import PaymentIn

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("", summary="Registrar pago")
def register_payment(payload: PaymentIn, db: Session = Depends(get_db)):
    return {"ok": True, "sale_id": payload.sale_id}
