import datetime
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.utils.atomic_file import atomic_write_text

router = APIRouter()

DATA_DIR = Path("data")
WALLET = DATA_DIR / "wallet.json"
LEDGER = DATA_DIR / "wallet_ledger.jsonl"
IDEM_STORE = DATA_DIR / "wallet_idem.json"


def _ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default


def _save_json(path, obj):
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    atomic_write_text(str(path), s)


class WalletOp(BaseModel):
    customer_id: int
    amount: float = Field(gt=0)


@router.get("/wallet/balance")
def wallet_balance(customer_id: int):
    _ensure_dirs()
    state = _load_json(WALLET, {})
    bal = float(state.get(str(customer_id), 0.0))
    return {"customer_id": customer_id, "balance": bal}


def _next_tx_id():
    try:
        with open(LEDGER, encoding="utf-8") as f:
            return sum(1 for _ in f) + 1
    except FileNotFoundError:
        return 1


def _append_ledger(entry):
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _idem_key(request: Request, kind: str):
    h = request.headers.get("Idempotency-Key") or request.headers.get("IdempotencyKey")
    return f"{kind}:{h}" if h else None


@router.post("/wallet/credit")
def wallet_credit(op: WalletOp, request: Request):
    _ensure_dirs()
    idem_map = _load_json(IDEM_STORE, {})
    ik = _idem_key(request, "credit")
    if ik and ik in idem_map:
        cached = idem_map[ik]
        if cached.get("customer_id") == op.customer_id and float(cached.get("amount")) == float(
            op.amount
        ):
            return cached["response"]

    state = _load_json(WALLET, {})
    key = str(op.customer_id)
    bal = float(state.get(key, 0.0))
    bal += float(op.amount)
    state[key] = round(bal, 2)

    tx_id = _next_tx_id()
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "customer_id": op.customer_id,
        "kind": "credit",
        "amount": float(op.amount),
        "tx_id": tx_id,
    }
    _append_ledger(entry)
    _save_json(WALLET, state)

    resp = {"tx_id": tx_id, "customer_id": op.customer_id, "balance": state[key]}
    if ik:
        idem_map[ik] = {"customer_id": op.customer_id, "amount": float(op.amount), "response": resp}
        _save_json(IDEM_STORE, idem_map)
    return resp


@router.post("/wallet/debit")
def wallet_debit(op: WalletOp, request: Request):
    _ensure_dirs()
    idem_map = _load_json(IDEM_STORE, {})
    ik = _idem_key(request, "debit")
    if ik and ik in idem_map:
        cached = idem_map[ik]
        if cached.get("customer_id") == op.customer_id and float(cached.get("amount")) == float(
            op.amount
        ):
            return cached["response"]

    state = _load_json(WALLET, {})
    key = str(op.customer_id)
    bal = float(state.get(key, 0.0))
    if bal < float(op.amount):
        raise HTTPException(status_code=409, detail="insufficient_funds")

    bal -= float(op.amount)
    state[key] = round(bal, 2)

    tx_id = _next_tx_id()
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "customer_id": op.customer_id,
        "kind": "debit",
        "amount": float(op.amount),
        "tx_id": tx_id,
    }
    _append_ledger(entry)
    _save_json(WALLET, state)

    resp = {"tx_id": tx_id, "customer_id": op.customer_id, "balance": state[key]}
    if ik:
        idem_map[ik] = {"customer_id": op.customer_id, "amount": float(op.amount), "response": resp}
        _save_json(IDEM_STORE, idem_map)
    return resp


@router.get("/wallet/ledger")
def wallet_ledger(customer_id: int | None = None, limit: int = 50):
    _ensure_dirs()
    out = []
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if customer_id is None or e.get("customer_id") == customer_id:
                        out.append(e)
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    out = out[-limit:]
    return {"count": len(out), "entries": out}
