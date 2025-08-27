from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os, sqlite3, json, datetime

router = APIRouter()

class ValidateBody(BaseModel):
    code: str
    order_subtotal: float
    customer_id: Optional[int] = None
    now_iso: Optional[str] = None

def _db_path():
    from app.db import engine
    p = engine.url.database
    if not os.path.isabs(p): p = os.path.abspath(p)
    return p

def _bitmask_allows(mask: Optional[int], dt: datetime.datetime) -> bool:
    if not mask or mask == 0:
        return True  # sin restricción de días
    # weekday(): Mon=0..Sun=6 -> usamos bit 0=Mon, ... bit 6=Sun
    return (mask & (1 << dt.weekday())) != 0

def _hours_allow(hours_json: Optional[str], dt: datetime.datetime) -> bool:
    if not hours_json:
        return True
    try:
        ranges = json.loads(hours_json)
    except Exception:
        return True
    if not isinstance(ranges, list) or not ranges:
        return True
    t = dt.time()
    for r in ranges:
        start = r.get("start")
        end = r.get("end")
        if not start or not end:
            continue
        try:
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
            s = datetime.time(sh, sm)
            e = datetime.time(eh, em)
            if s <= t <= e:
                return True
        except Exception:
            continue
    return False

def _audit(con: sqlite3.Connection, coupon_id: int, event: str, by_user: str, notes: str):
    cur = con.cursor()
    cur.execute(
        "INSERT INTO coupon_audit (coupon_id, event, at, by_user, notes) VALUES (?,?,?,?,?)",
        (coupon_id, event, datetime.datetime.utcnow().isoformat(timespec="seconds"), by_user, notes[:250])
    )
    con.commit()

@router.post("/validate")
def validate_coupon(body: ValidateBody, x_user: Optional[str] = Header(default="demo", alias="X-User", convert_underscores=False)):
    dbp = _db_path()
    con = sqlite3.connect(dbp)
    cur = con.cursor()

    code = (body.code or "").strip().upper()
    if not code:
        con.close()
        raise HTTPException(status_code=400, detail="COUPON_CODE_REQUIRED")

    row = cur.execute(
        """SELECT id, code, type, value, min_amount, max_uses, used_count,
                         valid_from, valid_to, valid_days_mask, valid_hours_json,
                         segment_id, is_active
           FROM coupon WHERE UPPER(code)=?""",
        (code,)
    ).fetchone()

    if not row:
        con.close()
        raise HTTPException(status_code=404, detail="COUPON_NOT_FOUND")

    (coupon_id, code_db, ctype, cvalue, min_amount, max_uses, used_count,
     valid_from, valid_to, days_mask, hours_json, segment_id, is_active) = row

    now = None
    if body.now_iso:
        try:
            now = datetime.datetime.fromisoformat(body.now_iso)
        except Exception:
            now = None
    if not now:
        now = datetime.datetime.utcnow()

    # Normalizaciones
    min_amount = float(min_amount or 0)
    used_count = int(used_count or 0)
    max_uses = int(max_uses) if (max_uses is not None) else None
    days_mask = int(days_mask) if (days_mask is not None) else None
    segment_id = int(segment_id) if (segment_id is not None) else None
    is_active = bool(is_active)

    # 1) activo
    if not is_active:
        _audit(con, coupon_id, "validate-fail", x_user, "INACTIVE")
        con.close()
        raise HTTPException(status_code=400, detail="COUPON_INACTIVE")

    # 2) fechas
    if valid_from and str(valid_from).strip():
        try:
            vf = datetime.datetime.fromisoformat(str(valid_from))
            if now < vf:
                _audit(con, coupon_id, "validate-fail", x_user, "NOT_YET_VALID")
                con.close()
                raise HTTPException(status_code=400, detail="COUPON_NOT_YET_VALID")
        except Exception:
            pass
    if valid_to and str(valid_to).strip():
        try:
            vt = datetime.datetime.fromisoformat(str(valid_to))
            if now > vt:
                _audit(con, coupon_id, "validate-fail", x_user, "EXPIRED")
                con.close()
                raise HTTPException(status_code=400, detail="COUPON_EXPIRED")
        except Exception:
            pass

    # 3) día/horario
    if not _bitmask_allows(days_mask, now):
        _audit(con, coupon_id, "validate-fail", x_user, "DAY_NOT_ALLOWED")
        con.close()
        raise HTTPException(status_code=400, detail="COUPON_DAY_NOT_ALLOWED")

    if not _hours_allow(hours_json, now):
        _audit(con, coupon_id, "validate-fail", x_user, "HOUR_NOT_ALLOWED")
        con.close()
        raise HTTPException(status_code=400, detail="COUPON_HOUR_NOT_ALLOWED")

    # 4) límite de usos
    if (max_uses is not None) and (used_count >= max_uses):
        _audit(con, coupon_id, "validate-fail", x_user, "MAX_USES_REACHED")
        con.close()
        raise HTTPException(status_code=400, detail="COUPON_MAX_USES_REACHED")

    # 5) segmento
    if segment_id:
        if body.customer_id is None:
            _audit(con, coupon_id, "validate-fail", x_user, "SEGMENT_REQUIRED")
            con.close()
            raise HTTPException(status_code=400, detail="COUPON_SEGMENT_REQUIRED")
        cust = cur.execute(
            "SELECT segment_id FROM customer WHERE id=?",
            (int(body.customer_id),)
        ).fetchone()
        if not cust or (int(cust[0] or 0) != segment_id):
            _audit(con, coupon_id, "validate-fail", x_user, "SEGMENT_MISMATCH")
            con.close()
            raise HTTPException(status_code=400, detail="COUPON_SEGMENT_MISMATCH")

    # 6) mínimo de compra
    subtotal = float(body.order_subtotal or 0)
    if subtotal < min_amount:
        _audit(con, coupon_id, "validate-fail", x_user, "MIN_AMOUNT_NOT_MET")
        con.close()
        raise HTTPException(status_code=400, detail="COUPON_MIN_AMOUNT_NOT_MET")

    # 7) cálculo de descuento
    ctype = (ctype or "").lower()
    value = float(cvalue or 0)
    discount = 0.0
    apply_as = None

    if ctype == "percent":
        discount = round(subtotal * (value / 100.0), 2)
        apply_as = "percent"
    elif ctype == "fixed":
        discount = round(min(value, subtotal), 2)
        apply_as = "fixed"
    else:
        _audit(con, coupon_id, "validate-fail", x_user, f"UNKNOWN_TYPE:{ctype}")
        con.close()
        raise HTTPException(status_code=400, detail="COUPON_TYPE_UNKNOWN")

    # Auditar validación OK (no incrementa usos aún)
    _audit(con, coupon_id, "validate-ok", x_user, f"apply_as={apply_as},disc={discount}")
    con.close()

    return {
        "coupon_id": coupon_id,
        "code": code_db,
        "valid": True,
        "apply_as": apply_as,
        "value": value,
        "discount": discount,
        "reason": "OK",
    }
