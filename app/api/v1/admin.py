from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/context", summary="Contexto de tienda")
def get_context():
    return {
        "store_id": settings.store_id,
        "store": settings.store_name,
        "currency": settings.currency,
        "tolerance": settings.cash_close_tolerance,
        "round_step": settings.cash_rounding_step,
        "cart_max": settings.cart_max,
    }
