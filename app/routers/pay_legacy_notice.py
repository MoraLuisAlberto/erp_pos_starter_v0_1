from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.post("/pay-legacy")
def pay_legacy_deprecated():
    raise HTTPException(status_code=410, detail="Deprecated: use /pos/order/pay")
