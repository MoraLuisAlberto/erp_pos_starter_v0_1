from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.utils.atomic_file import append_jsonl_atomic, write_json_atomic

router = APIRouter()

BALANCES = Path("data/wallet_balances.json")
LEDGER = Path("data/wallet_ledger.jsonl")


# carga/guarda balances (archivo pequeño)
def _load_balances() -> Dict[str, float]:
    if not BALANCES.exists():
        return {}
    try:
        return json.loads(BALANCES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_balances(bal: Dict[str, float]) -> None:
    write_json_atomic(BALANCES, bal)


def _append_ledger(entry: Dict[str, Any]) -> None:
    append_jsonl_atomic(LEDGER, entry)


# Idempotencia simple en memoria (TTL 1h). Solo cachea 200 OK.
_IDEM: Dict[str, Dict[str, Any]] = {}
_IDEM_EXP: Dict[str, float] = {}
_IDEM_TTL = 3600.0


def _idem_get(key: Optional[str]) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    exp = _IDEM_EXP.get(key, 0)
    if exp < time.time():
        _IDEM.pop(key, None)
        _IDEM_EXP.pop(key, None)
        return None
    return _IDEM.get(key)


def _idem_set(key: Optional[str], value: Dict[str, Any]) -> None:
    if not key:
        return
    _IDEM[key] = value
    _IDEM_EXP[key] = time.time() + _IDEM_TTL


# ====== Schemas ======
class CreditReq(BaseModel):
    customer_id: int = Field(..., gt=0)
    amount: float = Field(..., gt=0)


class DebitReq(BaseModel):
    customer_id: int = Field(..., gt=0)
    amount: float = Field(..., gt=0)


class TxResp(BaseModel):
    ok: bool
    tx_id: str
    customer_id: int
    amount: float
    balance: float
    replay: bool = False


# ====== Endpoints ======
@router.get("/wallet/balance")
def wallet_balance(customer_id: int):
    bal = _load_balances()
    return {"customer_id": customer_id, "balance": float(bal.get(str(customer_id), 0.0))}


@router.get("/wallet/ledger")
def wallet_ledger(customer_id: Optional[int] = None, limit: int = 50):
    limit = max(1, min(1000, limit))
    entries: List[Dict[str, Any]] = []
    if LEDGER.exists():
        # lee últimas líneas (simple: carga todo y recorta al final)
        lines = LEDGER.read_text(encoding="utf-8").splitlines()
        for line in lines[-2000:]:
            try:
                e = json.loads(line)
                entries.append(e)
            except Exception:
                continue
    if customer_id is not None:
        entries = [e for e in entries if e.get("customer_id") == customer_id]
    return {"count": len(entries[-limit:]), "entries": entries[-limit:]}


@router.post("/wallet/credit", response_model=TxResp)
def wallet_credit(
    req: CreditReq,
    Idempotency_Key: Optional[str] = Header(default=None, convert_underscores=True),
):
    # idempotent replay
    cached = _idem_get(Idempotency_Key)
    if cached:
        return {**cached, "replay": True}

    bal = _load_balances()
    key = str(req.customer_id)
    new_balance = float(bal.get(key, 0.0)) + float(req.amount)
    bal[key] = new_balance
    _save_balances(bal)

    tx_id = f"WL{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "kind": "credit",
        "customer_id": req.customer_id,
        "amount": float(req.amount),
        "balance_after": new_balance,
        "idempotency_key": Idempotency_Key,
        "tx_id": tx_id,
    }
    _append_ledger(entry)

    resp = {
        "ok": True,
        "tx_id": tx_id,
        "customer_id": req.customer_id,
        "amount": float(req.amount),
        "balance": new_balance,
        "replay": False,
    }
    _idem_set(Idempotency_Key, resp)
    return resp


@router.post("/wallet/debit", response_model=TxResp)
def wallet_debit(
    req: DebitReq,
    Idempotency_Key: Optional[str] = Header(default=None, convert_underscores=True),
):
    # idempotent replay
    cached = _idem_get(Idempotency_Key)
    if cached:
        return {**cached, "replay": True}

    bal = _load_balances()
    key = str(req.customer_id)
    current = float(bal.get(key, 0.0))
    amt = float(req.amount)
    if amt > current + 1e-9:
        raise HTTPException(status_code=409, detail="insufficient_funds")

    new_balance = current - amt
    bal[key] = new_balance
    _save_balances(bal)

    tx_id = f"WL{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "kind": "debit",
        "customer_id": req.customer_id,
        "amount": amt,
        "balance_after": new_balance,
        "idempotency_key": Idempotency_Key,
        "tx_id": tx_id,
    }
    _append_ledger(entry)

    resp = {
        "ok": True,
        "tx_id": tx_id,
        "customer_id": req.customer_id,
        "amount": amt,
        "balance": new_balance,
        "replay": False,
    }
    _idem_set(Idempotency_Key, resp)
    return resp
