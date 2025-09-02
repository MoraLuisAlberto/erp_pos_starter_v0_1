from fastapi import APIRouter

from app.core.schemas import CouponCheck

router = APIRouter(prefix="/coupons", tags=["coupons"])


@router.post("/validate", summary="Validar cupón en POS")
def validate_coupon(payload: CouponCheck):
    return {"valid": True, "amount": 0.0, "type": "percent"}
