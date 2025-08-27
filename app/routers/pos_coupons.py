from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Literal, Optional, List, Dict, Tuple, Any
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, time, timezone
from pathlib import Path
import json

router = APIRouter(prefix="/pos/coupon", tags=["pos", "coupon"])

def money(v: Decimal) -> Decimal:
    return (v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if isinstance(v, Decimal) else Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

# === Reglas MVP + nuevas (vigencia y weekdays) ===
# weekdays: 0..6 = Mon..Sun; también acepta ["mon","sat",...]
COUPONS: Dict[str, Dict[str, Any]] = {
    "TEST10":   {"type": "percent", "value": Decimal("10"),  "min_amount": Decimal("100.00"), "max_uses": 1},
    "SAVE50":   {"type": "amount",  "value": Decimal("50.00"), "min_amount": Decimal("200.00"), "max_uses": 1},
    "NITE20":   {"type": "percent", "value": Decimal("20"),  "hours": (time(18,0,0), time(23,59,59)), "max_uses": 3},
    # Nuevos ejemplos de vigencia:
    "WEEKEND15":{ "type":"percent", "value": Decimal("15"), "weekdays":[5,6] },  # sáb(5), dom(6)
    "DATED5":   { "type":"amount",  "value": Decimal("5.00"), "start_date":"2025-08-20", "end_date":"2025-08-31" },
}

# === Data dirs ===
_DATA_DIR = Path("data"); _DATA_DIR.mkdir(parents=True, exist_ok=True)

# Uso por (code, customer_id)
_USAGE: Dict[Tuple[str, int], int] = {}
_USAGE_FILE = _DATA_DIR / "coupons_usage.json"

def _usage_save():
    try:
        entries = [{"code": c, "customer_id": uid, "used": used} for (c, uid), used in _USAGE.items()]
        with _USAGE_FILE.open("w", encoding="utf-8") as f:
            json.dump({"entries": entries}, f, ensure_ascii=False)
    except Exception:
        pass

def _usage_load():
    try:
        if not _USAGE_FILE.exists():
            return
        with _USAGE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        _USAGE.clear()
        for it in (data.get("entries") or []):
            code = (it.get("code") or "").strip().upper()
            uid  = it.get("customer_id")
            used = int(it.get("used", 0))
            if code and uid is not None:
                _USAGE[(code, int(uid))] = used
    except Exception:
        _USAGE.clear()

_usage_load()

# === Auditoría persistente (JSONL) ===
_AUDIT_FILE = _DATA_DIR / "coupons_audit.jsonl"
_AUD_SEEN_PIDS = set()  # dedupe por payment_id

def _audit_write(event: dict):
    try:
        event = dict(event)
        event["ts"] = datetime.now(timezone.utc).isoformat()
        with _AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except Exception:
        pass

# Helpers de uso
def usage_get(code_up: str, customer_id: Optional[int]):
    rule = COUPONS.get(code_up)
    if (not rule) or (customer_id is None) or ("max_uses" not in rule):
        return 0, None, None
    used = _USAGE.get((code_up, int(customer_id)), 0)
    max_uses = int(rule["max_uses"])
    remaining = max(max_uses - used, 0)
    return used, max_uses, remaining

def usage_inc_if_possible(code_up: str, customer_id: Optional[int]) -> bool:
    rule = COUPONS.get(code_up)
    if (not rule) or (customer_id is None) or ("max_uses" not in rule):
        return True
    used, max_uses, remaining = usage_get(code_up, customer_id)
    if remaining is None:
        return True
    if remaining <= 0:
        return False
    _USAGE[(code_up, int(customer_id))] = used + 1
    _usage_save()
    return True

# === Nuevos helpers: fechas y weekdays ===
_WD_MAP = {"mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}

def _norm_weekdays(wd):
    if wd is None:
        return None
    out = []
    for x in wd:
        if isinstance(x, int):
            if 0 <= x <= 6: out.append(x)
        else:
            k = str(x).strip().lower()
            if k in _WD_MAP: out.append(_WD_MAP[k])
    return sorted(set(out))

def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s: return None
    try: return date.fromisoformat(str(s))
    except Exception: return None

def in_time_window(at: datetime, window):
    t = at.time(); start, end = window
    return (t >= start) and (t <= end)

class CouponItem(BaseModel):
    product_id: Optional[int] = None
    sku: Optional[str] = None
    qty: Decimal
    unit_price: Optional[Decimal] = None
    price: Optional[Decimal] = None
    @field_validator("qty", mode="before")
    @classmethod
    def _qty_to_decimal(cls, v): return Decimal(str(v))
    @field_validator("unit_price", "price", mode="before")
    @classmethod
    def _money_to_decimal(cls, v):
        if v is None: return v
        return Decimal(str(v))

class CouponValidateRequest(BaseModel):
    code: Optional[str] = None
    amount: Optional[Decimal] = None
    session_id: Optional[int] = None
    order_id: Optional[int] = None
    customer_id: Optional[int] = None
    items: Optional[List[CouponItem]] = None
    coupon: Optional[dict] = None
    at: Optional[str] = None  # ISO8601

class CouponValidateResponse(BaseModel):
    valid: bool
    code: str
    discount_type: Literal["percent","amount","none"]
    discount_value: Optional[Decimal] = None
    discount_amount: Decimal
    new_total: Decimal
    reason: Optional[str] = None
    usage_remaining: Optional[int] = None

def compute_coupon_result(code: str, amount: Decimal, at_dt: Optional[datetime] = None, customer_id: Optional[int] = None) -> Dict:
    amount = money(amount)
    code_up = (code or "").strip().upper()
    rule = COUPONS.get(code_up)
    if rule is None:
        return {"valid": False, "code": code_up, "discount_type": "none",
                "discount_value": None, "discount_amount": Decimal("0.00"),
                "new_total": amount, "reason": "code_not_found", "usage_remaining": None}

    used, max_uses, remaining = usage_get(code_up, customer_id)
    if max_uses is not None and remaining is not None and remaining <= 0:
        dtype = "percent" if rule["type"] == "percent" else ("amount" if rule["type"] == "amount" else "none")
        dval  = rule.get("value")
        return {"valid": False, "code": code_up, "discount_type": dtype,
                "discount_value": dval, "discount_amount": Decimal("0.00"),
                "new_total": amount, "reason": "usage_limit_reached", "usage_remaining": 0}

    # Tiempo de evaluación
    if at_dt is None:
        at_dt = datetime.now()

    # Ventana de fechas (inclusive)
    sd = _parse_date(rule.get("start_date"))
    ed = _parse_date(rule.get("end_date"))
    if sd or ed:
        d = at_dt.date()
        if (sd and d < sd) or (ed and d > ed):
            dtype = "percent" if rule["type"] == "percent" else ("amount" if rule["type"] == "amount" else "none")
            dval  = rule.get("value")
            return {"valid": False, "code": code_up, "discount_type": dtype,
                    "discount_value": dval, "discount_amount": Decimal("0.00"),
                    "new_total": amount, "reason": "date_window_not_met", "usage_remaining": remaining}

    # Días de semana
    wd = _norm_weekdays(rule.get("weekdays"))
    if wd is not None and len(wd) > 0:
        if at_dt.weekday() not in wd:
            dtype = "percent" if rule["type"] == "percent" else ("amount" if rule["type"] == "amount" else "none")
            dval  = rule.get("value")
            return {"valid": False, "code": code_up, "discount_type": dtype,
                    "discount_value": dval, "discount_amount": Decimal("0.00"),
                    "new_total": amount, "reason": "weekday_not_allowed", "usage_remaining": remaining}

    # Horarios dentro del día
    if rule.get("hours"):
        if not in_time_window(at_dt, rule["hours"]):
            dtype = "percent" if rule["type"] == "percent" else ("amount" if rule["type"] == "amount" else "none")
            dval  = rule.get("value")
            return {"valid": False, "code": code_up, "discount_type": dtype,
                    "discount_value": dval, "discount_amount": Decimal("0.00"),
                    "new_total": amount, "reason": "time_window_not_met", "usage_remaining": remaining}

    # Mínimo de compra
    min_amt = rule.get("min_amount")
    if min_amt is not None and amount < min_amt:
        dtype = "percent" if rule["type"] == "percent" else ("amount" if rule["type"] == "amount" else "none")
        dval  = rule.get("value")
        return {"valid": False, "code": code_up, "discount_type": dtype,
                "discount_value": dval, "discount_amount": Decimal("0.00"),
                "new_total": amount, "reason": "min_amount_not_met", "usage_remaining": remaining}

    # Cálculo de descuento
    dtype = rule["type"]
    if dtype == "percent":
        dval = Decimal(str(rule["value"]))
        discount_amount = money(amount * (dval / Decimal("100")))
    elif dtype == "amount":
        dval = money(Decimal(str(rule["value"])))
        discount_amount = dval if dval <= amount else amount
    else:
        dval = None; discount_amount = Decimal("0.00")

    new_total = money(amount - discount_amount)
    return {"valid": True, "code": code_up, "discount_type": dtype,
            "discount_value": dval, "discount_amount": discount_amount,
            "new_total": new_total, "reason": None, "usage_remaining": remaining}

@router.post("/validate", response_model=CouponValidateResponse)
def validate_coupon(payload: CouponValidateRequest = Body(...)):
    code = (payload.code or (payload.coupon or {}).get("code") if payload.coupon else payload.code)
    if not code:
        raise HTTPException(status_code=422, detail=[{"type":"missing","loc":["body","code"],"msg":"Field required","input":None}])

    amount = payload.amount
    if amount is None and payload.items:
        total = Decimal("0")
        for it in payload.items:
            unit = it.unit_price if it.unit_price is not None else (it.price if it.price is not None else Decimal("0"))
            total += (it.qty * unit)
        amount = total
    if amount is None:
        raise HTTPException(status_code=422, detail=[{"type":"missing","loc":["body","amount"],"msg":"Field required (or provide items)","input":None}])

    at_dt: Optional[datetime] = None
    if payload.at:
        try: at_dt = datetime.fromisoformat(payload.at)
        except Exception: at_dt = None

    res = compute_coupon_result(code, amount, at_dt, payload.customer_id)
    try:
        _audit_write({
            "kind": "validate",
            "code": (res["code"]),
            "customer_id": (payload.customer_id if payload.customer_id is not None else None),
            "order_id": payload.order_id,
            "session_id": payload.session_id,
            "amount": str(amount),
            "result": res
        })
    except Exception:
        pass
    return CouponValidateResponse(**res)

# Export utils (usadas por otros routers)
def coupon_usage_get(code_up: str, customer_id: Optional[int]):
    return usage_get(code_up, customer_id)

def coupon_usage_inc(code_up: str, customer_id: Optional[int]) -> bool:
    return usage_inc_if_possible(code_up, customer_id)

# ===== DEV ONLY: reset/inspect usage =====
@router.post("/dev/reset-usage")
def dev_reset_usage(payload: dict = Body(...)):
    code = (payload or {}).get("code")
    cust = (payload or {}).get("customer_id")
    reset_all = bool((payload or {}).get("reset_all", False))
    cleared = 0
    if reset_all:
        cleared = len(_USAGE)
        _USAGE.clear()
        _usage_save()
        return {"ok": True, "cleared": cleared, "scope": "all"}
    keys = list(_USAGE.keys())
    for k in keys:
        c, uid = k
        if code and c != str(code).strip().upper(): continue
        if cust is not None and uid != int(cust): continue
        _USAGE.pop(k, None); cleared += 1
    _usage_save()
    return {"ok": True, "cleared": cleared, "scope": {"code": code, "customer_id": cust}}

@router.get("/dev/usage")
def dev_usage(code: Optional[str] = Query(default=None), customer_id: Optional[int] = Query(default=None)):
    out = []
    for (c, uid), used in _USAGE.items():
        if code and c != str(code).strip().upper(): continue
        if customer_id is not None and uid != int(customer_id): continue
        _, max_uses, remaining = usage_get(c, uid)
        out.append({"code": c, "customer_id": uid, "used": used, "max_uses": max_uses, "remaining": remaining})
    return {"entries": out}

@router.get("/dev/usage-path")
def dev_usage_path():
    try:
        p = _USAGE_FILE.resolve()
    except Exception:
        p = _USAGE_FILE
    exists = _USAGE_FILE.exists()
    size = _USAGE_FILE.stat().st_size if exists else 0
    return {"path": str(p), "exists": exists, "size": size}

# ===== Auditoría DEV =====
@router.get("/dev/audit-path")
def dev_audit_path():
    try:
        p = _AUDIT_FILE.resolve()
    except Exception:
        p = _AUDIT_FILE
    exists = _AUDIT_FILE.exists()
    size = _AUDIT_FILE.stat().st_size if exists else 0
    return {"path": str(p), "exists": exists, "size": size}

@router.get("/dev/audit-tail")
def dev_audit_tail(n: int = 50):
    out = []
    if _AUDIT_FILE.exists():
        try:
            with _AUDIT_FILE.open("r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines[-max(0, n):]:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    out.append({"_raw": line})
        except Exception:
            pass
    return {"count": len(out), "events": out}

@router.post("/dev/log-paid")
def dev_log_paid(payload: dict = Body(...)):
    """
    body: { code, customer_id, order_id, payment_id, base_total, paid_total, idempotency_key? }
    """
    pid = str((payload or {}).get("payment_id"))
    if not pid or pid == "None":
        raise HTTPException(status_code=422, detail="payment_id required")
    if pid in _AUD_SEEN_PIDS:
        return {"ok": True, "dedup": True}
    _AUD_SEEN_PIDS.add(pid)
    _audit_write({
        "kind": "paid",
        "code": (payload or {}).get("code"),
        "customer_id": (payload or {}).get("customer_id"),
        "order_id": (payload or {}).get("order_id"),
        "payment_id": (payload or {}).get("payment_id"),
        "base_total": (payload or {}).get("base_total"),
        "paid_total": (payload or {}).get("paid_total"),
        "idempotency_key": (payload or {}).get("idempotency_key")
    })
    return {"ok": True}
