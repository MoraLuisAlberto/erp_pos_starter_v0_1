from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter(tags=["health"])

@router.get("/health", operation_id="health_v1")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

