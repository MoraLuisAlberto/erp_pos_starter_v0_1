from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/limits", summary="Límites de cola offline")
def sync_limits():
    return {
        "soft": {"ops": settings.offline_soft_ops, "hours": settings.offline_soft_hours},
        "hard": {"ops": settings.offline_max_ops, "hours": settings.offline_max_hours},
    }
