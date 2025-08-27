from fastapi import APIRouter, Query, Response
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timezone
from app.utils.atomic_file import write_json_atomic, append_jsonl_atomic
import json
import io
import csv



from app.routers.pos_coupons import _AUDIT_FILE  # ruta del archivo

router = APIRouter(prefix="/reports/coupon", tags=["reports", "coupon"])

def _iter_audit():
    if not _AUDIT_FILE.exists():
        return
    with _AUDIT_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue

def _parse_ts(ts: str) -> Optional[datetime]:
    if not ts: 
        return None
    try:
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except Exception:
        return None

@router.get("/audit/today")
def audit_today(mode: str = Query(default="utc", pattern="^(utc|local|all)$")):
    """
    Snapshot de 'hoy' (UTC por defecto).
    """
    file_exists = _AUDIT_FILE.exists()
    total_lines = 0
    events: List[Dict[str, Any]] = []

    if not file_exists:
        return {"date": datetime.now(timezone.utc).date().isoformat(),
                "mode": mode, "file_exists": False, "raw_count": 0, "events": []}

    today_utc = datetime.now(timezone.utc).date()
    today_local = date.today()

    def want(dt: datetime) -> bool:
        if mode == "all":
            return True
        if mode == "utc":
            return dt.astimezone(timezone.utc).date() == today_utc
        else:
            return dt.date() == today_local

    for obj in _iter_audit():
        total_lines += 1
        dt = _parse_ts(obj.get("ts"))
        if not dt:
            continue
        if want(dt):
            events.append(obj)

    return {
        "date": (today_utc if mode == "utc" else today_local).isoformat(),
        "mode": mode,
        "file_exists": True,
        "raw_count": total_lines,
        "events": events
    }

def _within_range(dt: datetime, start_d: date, end_d: date, mode: str) -> bool:
    # rango inclusivo [start, end]
    if mode == "utc":
        d = dt.astimezone(timezone.utc).date()
    else:
        d = dt.date()
    return (d >= start_d) and (d <= end_d)

@router.get("/audit/range")
def audit_range(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    mode: str = Query(default="utc", pattern="^(utc|local|all)$")
):
    """
    Devuelve eventos y un resumen por código y por tipo en el rango [start, end] (inclusive).
    mode=utc (default) compara por fecha UTC; local usa la zona local; all no filtra.
    """
    file_exists = _AUDIT_FILE.exists()
    if not file_exists:
        return {"file_exists": False, "events": [], "summary": {}}

    try:
        start_d = date.fromisoformat(start)
        end_d   = date.fromisoformat(end)
    except Exception:
        return {"file_exists": True, "error": "invalid_date"}

    events: List[Dict[str, Any]] = []
    by_kind: Dict[str, int] = {}
    by_code: Dict[str, Dict[str, Any]] = {}

    for obj in _iter_audit():
        dt = _parse_ts(obj.get("ts"))
        if not dt:
            continue
        if mode != "all" and not _within_range(dt, start_d, end_d, mode):
            continue
        events.append(obj)
        k = str(obj.get("kind") or "unknown")
        by_kind[k] = by_kind.get(k, 0) + 1
        code = str(obj.get("code") or "NONE").upper()
        bc = by_code.setdefault(code, {"validate": 0, "paid": 0, "customers": set()})
        if k in ("validate", "paid"):
            bc[k] = bc.get(k, 0) + 1
        cust = obj.get("customer_id")
        if cust is not None:
            try:
                bc["customers"].add(int(cust))
            except Exception:
                pass

    # post-proceso counts y conversión
    out_codes = []
    for code, agg in by_code.items():
        customers = len(agg["customers"]) if isinstance(agg.get("customers"), set) else 0
        validate_c = int(agg.get("validate", 0))
        paid_c = int(agg.get("paid", 0))
        conv = (paid_c / validate_c) if validate_c > 0 else None
        out_codes.append({
            "code": code, "validate": validate_c, "paid": paid_c,
            "customers": customers, "conversion": conv
        })

    return {
        "file_exists": True,
        "range": {"start": start, "end": end, "mode": mode},
        "counts": {"total": len(events), "by_kind": by_kind},
        "by_code": out_codes
    }

@router.get("/audit/export.csv")
def audit_export_csv(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    mode: str = Query(default="utc", pattern="^(utc|local|all)$")
):
    """
    Exporta CSV con columnas útiles.
    """
    if not _AUDIT_FILE.exists():
        return Response(content="", media_type="text/csv")

    try:
        start_d = date.fromisoformat(start)
        end_d   = date.fromisoformat(end)
    except Exception:
        return Response(content="error: invalid_date", media_type="text/plain", status_code=400)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ts","kind","code","customer_id","order_id","payment_id","base_total","paid_total","idempotency_key"])

    for obj in _iter_audit():
        dt = _parse_ts(obj.get("ts"))
        if not dt:
            continue
        if mode != "all" and not _within_range(dt, start_d, end_d, mode):
            continue
        w.writerow([
            obj.get("ts") or "",
            obj.get("kind") or "",
            (str(obj.get("code") or "").upper()),
            obj.get("customer_id") or "",
            obj.get("order_id") or "",
            obj.get("payment_id") or "",
            obj.get("base_total") or "",
            obj.get("paid_total") or "",
            obj.get("idempotency_key") or ""
        ])

    csv_text = buf.getvalue()
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="coupon_audit.csv"'}
    )
