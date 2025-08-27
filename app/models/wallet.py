cd C:\Proyectos\erp-pos\erp_pos_starter_v0_1
. .\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path

@'
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..db import SessionLocal

router = APIRouter()
reports = APIRouter()

# ------------- Helpers SQL “planos” (evitan circular imports) -------------
def _get_wallet(db: Session, customer_id: int):
    row = db.execute(text("SELECT id, balance, status FROM wallet WHERE customer_id=:c"), {"c": customer_id}).fetchone()
    return row

def _ensure_wallet(db: Session, customer_id: int):
    row = _get_wallet(db, customer_id)
    if row: return row
    db.execute(text("INSERT INTO wallet(customer_id,balance,status) VALUES(:c,0,'active')"), {"c": customer_id})
    db.commit()
    return _get_wallet(db, customer_id)

def _deposit(db: Session, wallet_id: int, amount: float, reason: str, key: Optional[str], by_user: str="demo"):
    if amount <= 0: raise HTTPException(422, "Monto de depósito inválido")
    if key:
        exists = db.execute(text("SELECT id FROM wallet_tx WHERE idempotency_key=:k"), {"k":key}).fetchone()
        if exists: return exists[0]
    db.execute(text("""
        INSERT INTO wallet_tx(wallet_id,kind,amount,sign,delta,reason,by_user,idempotency_key)
        VALUES (:w,'deposit',:a, +1, :a, :r, :u, :k)
    """), {"w":wallet_id, "a":amount, "r":reason, "u":by_user, "k":key})
    db.execute(text("UPDATE wallet SET balance = balance + :a WHERE id=:w"), {"a": amount, "w": wallet_id})
    db.commit()
    txid = db.execute(text("SELECT id FROM wallet_tx WHERE idempotency_key=:k"), {"k":key}).scalar() if key else db.execute(text("SELECT last_insert_rowid()")).scalar()
    return txid

def _redeem(db: Session, wallet_id: int, amount: float, reason: str, order_id: int, key: Optional[str], by_user: str="demo"):
    if amount <= 0: raise HTTPException(422, "Monto a aplicar inválido")
    bal = db.execute(text("SELECT balance FROM wallet WHERE id=:w"), {"w": wallet_id}).scalar() or 0.0
    if amount > bal + 1e-9: raise HTTPException(422, f"Saldo insuficiente: {bal}")
    if key:
        exists = db.execute(text("SELECT id FROM wallet_tx WHERE idempotency_key=:k"), {"k":key}).fetchone()
        if exists: return exists[0]
    db.execute(text("""
        INSERT INTO wallet_tx(wallet_id,kind,amount,sign,delta,reason,order_id,by_user,idempotency_key)
        VALUES (:w,'redeem',:a, -1, -:a, :r, :o, :u, :k)
    """), {"w":wallet_id, "a":amount, "r":reason, "o":order_id, "u":by_user, "k":key})
    db.execute(text("UPDATE wallet SET balance = balance - :a WHERE id=:w"), {"a": amount, "w": wallet_id})
    db.commit()
    txid = db.execute(text("SELECT id FROM wallet_tx WHERE idempotency_key=:k"), {"k":key}).scalar() if key else db.execute(text("SELECT last_insert_rowid()")).scalar()
    return txid

# --------------------------- Schemas --------------------------------------
class LinkReq(BaseModel):
    customer_id: int

class DepositReq(BaseModel):
    customer_id: int
    amount: float = Field(gt=0)
    reason: str = "manual"
    by_user: str = "demo"

class ApplyCalcReq(BaseModel):
    order_id: int
    customer_id: int

# --------------------------- Endpoints ------------------------------------
@router.post("/wallet/link")
def link_wallet(payload: LinkReq):
    db = SessionLocal()
    try:
        w = _ensure_wallet(db, payload.customer_id)
        return {"customer_id": payload.customer_id, "wallet_id": w[0], "balance": float(w[1]), "status": w[2]}
    finally:
        db.close()

@router.get("/wallet/{customer_id}/balance")
def balance(customer_id: int):
    db = SessionLocal()
    try:
        w = _ensure_wallet(db, customer_id)
        return {"customer_id": customer_id, "wallet_id": w[0], "balance": float(w[1]), "status": w[2]}
    finally:
        db.close()

@router.post("/wallet/deposit")
def deposit(payload: DepositReq, x_idempotency_key: str | None = Header(default=None)):
    db = SessionLocal()
    try:
        w = _ensure_wallet(db, payload.customer_id)
        txid = _deposit(db, w[0], float(payload.amount), payload.reason, x_idempotency_key, payload.by_user)
        bal = db.execute(text("SELECT balance FROM wallet WHERE id=:w"), {"w": w[0]}).scalar()
        return {"ok": True, "tx_id": txid, "balance": float(bal)}
    finally:
        db.close()

@router.post("/wallet/apply-calc")
def apply_calc(payload: ApplyCalcReq):
    db = SessionLocal()
    try:
        w = _ensure_wallet(db, payload.customer_id)
        bal = float(w[1] or 0.0)
        total = db.execute(text("SELECT COALESCE(total, 0) FROM pos_order WHERE id=:o"), {"o": payload.order_id}).scalar() or 0.0
        can = float(min(bal, total))
        return {"order_id": payload.order_id, "customer_id": payload.customer_id, "balance": bal, "can_apply": can}
    finally:
        db.close()

# Reporte diario muy simple (depósitos/redenciones por día)
@reports.get("/wallet/daily")
def wallet_daily(date_str: str | None = None):
    db = SessionLocal()
    try:
        d = date.fromisoformat(date_str) if date_str else date.today()
        start = f"{d} 00:00:00"; end = f"{d} 23:59:59"
        row = db.execute(text("""
            SELECT
              SUM(CASE WHEN kind='deposit' THEN amount ELSE 0 END) AS deposits,
              SUM(CASE WHEN kind='redeem' THEN amount ELSE 0 END) AS redeems
            FROM wallet_tx
            WHERE created_at BETWEEN :a AND :b
        """), {"a": start, "b": end}).fetchone()
        return {"date": str(d), "deposits": float(row[0] or 0.0), "redeems": float(row[1] or 0.0)}
    finally:
        db.close()

# -------- Helpers para que POS/Pay pueda redimir de forma segura ----------
def redeem_in_pos(db: Session, customer_id: int, amount: float, order_id: int, key: str | None, by_user: str = "demo"):
    w = _ensure_wallet(db, customer_id)
    return _redeem(db, w[0], float(amount), "pos-pay", order_id, key, by_user)
'@ | Set-Content -Encoding UTF8 .\app\routers\wallet.py
