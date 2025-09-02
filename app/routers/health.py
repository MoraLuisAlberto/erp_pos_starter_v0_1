from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", operation_id="health_v1")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
