from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.schemas import SaleCreate
from app.core.config import settings

router = APIRouter(prefix="/sales", tags=["sales"])

@router.post("", summary="Crear venta")
def create_sale(payload: SaleCreate, db: Session = Depends(get_db)):
    return {"ok": True, "id": 1, "round_step": settings.cash_rounding_step}
