from fastapi import APIRouter, Header, Depends
from sqlalchemy.orm import Session
from typing import Optional

from .pay_guarded import pay_guarded, PayBody
from ..db import get_db

router = APIRouter()

@router.post("/pay")
def pay_alias(
    body: PayBody,
    x_idem: Optional[str] = Header(
        default=None,
        alias="X-Idempotency-Key",
        convert_underscores=False
    ),
    db: Session = Depends(get_db),
):
    # Reusar la lógica del endpoint principal, pero ya con db inyectado
    return pay_guarded(body, x_idem, db)
