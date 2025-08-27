from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import text
from typing import Any, Dict
from app.db import get_db

# OJO: este router se monta con prefix="/pos" en main.py ⇒ rutas reales: /pos/session/*
router = APIRouter(prefix="/session", tags=["pos-session"])

def _row_to_dict(row) -> Dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)

# ---------- OPEN ----------
@router.post("/open")
def open_session(payload: Dict[str, Any] = Body(...), db: OrmSession = Depends(get_db)):
    store_id = int(payload.get("store_id") or 1)
    terminal_id = payload.get("terminal_id")
    if terminal_id is None:
        terminal_id = 1
    terminal_id = int(terminal_id)
    user_open_id = int(payload.get("user_open_id") or 1)
    opened_by = str(payload.get("opened_by") or "demo")
    opening_cash = float(payload.get("opening_cash") or 0)

    db.execute(text("CREATE TABLE IF NOT EXISTS pos_store (id INTEGER PRIMARY KEY, name TEXT)"))
    db.execute(text("CREATE TABLE IF NOT EXISTS pos_terminal (id INTEGER PRIMARY KEY, store_id INTEGER, name TEXT)"))
    db.execute(text("INSERT OR IGNORE INTO pos_store(id,name) VALUES (1,'Main')"))
    db.execute(text("INSERT OR IGNORE INTO pos_terminal(id,store_id,name) VALUES (1,1,'T1')"))

    db.execute(text("""
        INSERT INTO pos_session(
          store_id, terminal_id, user_open_id, opened_at, status,
          user_close_id, closed_at, idempotency_open, idempotency_close,
          audit_ref, opened_by, closed_by, note,
          expected_cash, counted_pre, counted_final, diff_cash, tolerance,
          idem_open, idem_close
        ) VALUES (
          :store_id, :terminal_id, :user_open_id, CURRENT_TIMESTAMP, 'open',
          NULL, NULL, NULL, NULL,
          'api', :opened_by, NULL, NULL,
          :expected_cash, 0, 0, 0, 0,
          NULL, NULL
        )
    """), {
        "store_id": store_id,
        "terminal_id": terminal_id,
        "user_open_id": user_open_id,
        "opened_by": opened_by,
        "expected_cash": opening_cash,
    })
    db.commit()

    row = db.execute(text("""
        SELECT id, status, opened_by, opened_at FROM pos_session
        WHERE status='open' ORDER BY id DESC LIMIT 1
    """)).fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="OPEN_FAILED")
    r = _row_to_dict(row)
    return {"id": r["id"], "status": r["status"], "opened_by": r["opened_by"], "opened_at": r["opened_at"]}

# ---------- CASH COUNT ----------
@router.post("/cash-count")
def cash_count(payload: Dict[str, Any] = Body(...), db: OrmSession = Depends(get_db)):
    sid = payload.get("session_id")
    if sid is None:
        raise HTTPException(status_code=422, detail="session_id required")
    try:
        sid = int(sid)
    except Exception:
        raise HTTPException(status_code=422, detail="session_id must be int")

    stage = payload.get("stage")
    kind = payload.get("kind")
    if stage is None and kind is not None:
        stage = kind
    if stage not in ("pre", "final"):
        raise HTTPException(status_code=422, detail="stage must be 'pre' or 'final'")
    if kind is None:
        kind = stage

    total = payload.get("total")
    if total is None:
        total = payload.get("amount")
    try:
        total = float(total if total is not None else 0.0)
    except Exception:
        raise HTTPException(status_code=422, detail="total/amount must be number")
    by_user = str(payload.get("by_user") or "demo")

    ses = db.execute(text("SELECT id, status FROM pos_session WHERE id=:sid"), {"sid": sid}).fetchone()
    if not ses:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    try:
        db.execute(text("""
            INSERT INTO cash_count (session_id, stage, created_at, by_user, kind, total, details_json, at)
            VALUES (:sid, :stage, CURRENT_TIMESTAMP, :by_user, :kind, :total, '[]', CURRENT_TIMESTAMP)
        """), {"sid": sid, "stage": stage, "by_user": by_user, "kind": kind, "total": total})
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="CASH_COUNT_FAILED")

    return {"session_id": sid, "stage": stage, "kind": kind, "amount": total, "total": total}

# ---------- RESUME ----------
@router.get("/{sid}/resume")
def resume_session(sid: int, db: OrmSession = Depends(get_db)):
    row = db.execute(text("""
        SELECT id, status, opened_by, opened_at, closed_by, closed_at,
               expected_cash, counted_pre, counted_final, diff_cash, tolerance
        FROM pos_session WHERE id=:sid
    """), {"sid": sid}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    s = _row_to_dict(row)

    pre_total = db.execute(text("""
        SELECT total FROM cash_count
        WHERE session_id=:sid AND stage='pre'
        ORDER BY id DESC LIMIT 1
    """), {"sid": sid}).scalar()
    fin_total = db.execute(text("""
        SELECT total FROM cash_count
        WHERE session_id=:sid AND stage='final'
        ORDER BY id DESC LIMIT 1
    """), {"sid": sid}).scalar()

    counted_pre = float(pre_total if pre_total is not None else s.get("counted_pre") or 0.0)
    counted_final = float(fin_total if fin_total is not None else s.get("counted_final") or 0.0)
    expected_cash = float(s.get("expected_cash") or 0.0)
    diff = (counted_final or 0.0) - expected_cash

    pre_list = db.execute(text("""
        SELECT id, total, by_user, created_at FROM cash_count
        WHERE session_id=:sid AND stage='pre'
        ORDER BY id DESC LIMIT 5
    """), {"sid": sid}).fetchall()
    fin_list = db.execute(text("""
        SELECT id, total, by_user, created_at FROM cash_count
        WHERE session_id=:sid AND stage='final'
        ORDER BY id DESC LIMIT 5
    """), {"sid": sid}).fetchall()

    to_simple = lambda rows: [
        {"id": r[0], "total": r[1], "by_user": r[2], "created_at": r[3]} for r in rows
    ]

    return {
        "session_id": s["id"],
        "status": s["status"],
        "opened_by": s["opened_by"],
        "opened_at": s["opened_at"],
        "closed_by": s["closed_by"],
        "closed_at": s["closed_at"],
        "expected_cash": expected_cash,
        "counted_pre": counted_pre,
        "counted_final": counted_final,
        "diff": diff,
        "tolerance": float(s.get("tolerance") or 0.0),
        "pre_count": to_simple(pre_list),
        "final_count": to_simple(fin_list),
    }

# ---------- CLOSE (idempotente) ----------
@router.post("/close")
def close_session(payload: Dict[str, Any] = Body(...), db: OrmSession = Depends(get_db)):
    """
    Cierra la sesión:
    - session_id requerido
    - Si viene total/amount, registra un cash_count(stage='final') antes de cerrar.
    - Idempotente: si ya está cerrada, devuelve el resumen actual.
    """
    sid = payload.get("session_id")
    if sid is None:
        raise HTTPException(status_code=422, detail="session_id required")
    try:
        sid = int(sid)
    except Exception:
        raise HTTPException(status_code=422, detail="session_id must be int")

    by_user = str(payload.get("by_user") or "demo")
    maybe_total = payload.get("total", payload.get("amount", None))
    if maybe_total is not None:
        try:
            maybe_total = float(maybe_total)
        except Exception:
            raise HTTPException(status_code=422, detail="total/amount must be number")

    ses = db.execute(text("""
        SELECT id, status, expected_cash, counted_pre, counted_final FROM pos_session WHERE id=:sid
    """), {"sid": sid}).fetchone()
    if not ses:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    sdict = _row_to_dict(ses)

    # Si ya está cerrada ⇒ resume actual
    if sdict.get("status") == "closed":
        return resume_session(sid, db)

    # Si nos pasaron total, registrar cash_count final
    if maybe_total is not None:
        db.execute(text("""
            INSERT INTO cash_count (session_id, stage, created_at, by_user, kind, total, details_json, at)
            VALUES (:sid, 'final', CURRENT_TIMESTAMP, :by_user, 'final', :total, '[]', CURRENT_TIMESTAMP)
        """), {"sid": sid, "by_user": by_user, "total": maybe_total})

    # Lee expected y final para calcular diff
    expected = db.execute(text("SELECT expected_cash FROM pos_session WHERE id=:sid"), {"sid": sid}).scalar() or 0.0
    final_total = db.execute(text("""
        SELECT total FROM cash_count WHERE session_id=:sid AND stage='final'
        ORDER BY id DESC LIMIT 1
    """), {"sid": sid}).scalar()
    counted_final = float(final_total if final_total is not None else sdict.get("counted_final") or 0.0)
    diff = counted_final - float(expected)

    # Cierra
    db.execute(text("""
        UPDATE pos_session
        SET status='closed', closed_by=:by_user, closed_at=CURRENT_TIMESTAMP,
            counted_final=:counted_final, diff_cash=:diff
        WHERE id=:sid
    """), {"sid": sid, "by_user": by_user, "counted_final": counted_final, "diff": diff})
    db.commit()

    # Devuelve el resumen (incluye listas de conteos)
    return resume_session(sid, db)
