from typing import Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from ..db import get_db
from .pay_guarded import PayBody, pay_guarded

router = APIRouter()


@router.post("/pay")
def pay_alias(
    body: PayBody,
    x_idem: Optional[str] = Header(
        default=None, alias="X-Idempotency-Key", convert_underscores=False
    ),
    db: Session = Depends(get_db),
):
    # Reusar la lógica del endpoint principal, pero ya con db inyectado
    return pay_guarded(body, x_idem, db)
