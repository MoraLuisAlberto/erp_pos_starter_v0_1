from datetime import date

from fastapi import APIRouter

# Reusamos estructuras del módulo de cupones
from app.routers.pos_coupons import _USAGE, usage_get

router = APIRouter(prefix="/reports/coupon", tags=["reports", "coupon"])


@router.get("/usage/daily")
def usage_daily():
    """
    Snapshot simple del uso de cupones (en memoria del proceso).
    Estructura:
    {
      date: "YYYY-MM-DD",
      entries: [{code, customer_id, used, max_uses, remaining}],
      summary_by_code: [{code, used_total, customers}]
    }
    """
    today = date.today().isoformat()
    entries = []
    for (code, cust), used in _USAGE.items():
        _, max_uses, remaining = usage_get(code, cust)
        entries.append(
            {
                "code": code,
                "customer_id": cust,
                "used": int(used),
                "max_uses": (int(max_uses) if max_uses is not None else None),
                "remaining": (int(remaining) if remaining is not None else None),
            }
        )

    summary = {}
    for e in entries:
        code = e["code"]
        if code not in summary:
            summary[code] = {"code": code, "used_total": 0, "customers": 0}
        summary[code]["used_total"] += int(e["used"])
        summary[code]["customers"] += 1

    return {"date": today, "entries": entries, "summary_by_code": list(summary.values())}
