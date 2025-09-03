import random
import time

import requests

BASE = "http://127.0.0.1:8010"


def _get(p, params=None):
    r = requests.get(f"{BASE}{p}", params=params, timeout=10)
    return r.status_code, r.json()


def _post(p, body, headers=None):
    r = requests.post(f"{BASE}{p}", json=body, headers=headers or {}, timeout=10)
    try:
        js = r.json()
    except Exception:
        js = {"text": r.text}
    return r.status_code, js


CUST = 233366


def test_wallet_credit_idempotent():
    st, bal0 = _get("/wallet/balance", {"customer_id": CUST})
    assert st == 200
    idem = "".join(random.choices("abcdef0123456789", k=12))
    body = {"customer_id": CUST, "amount": 10.0}
    h = {"Idempotency-Key": idem}

    st1, j1 = _post("/wallet/credit", body, h)
    assert st1 == 200
    st2, j2 = _post("/wallet/credit", body, h)
    assert st2 == 200
    assert j1["tx_id"] == j2["tx_id"] and j2["replay"] is True

    st, bal1 = _get("/wallet/balance", {"customer_id": CUST})
    assert st == 200
    assert abs(bal1["balance"] - (bal0["balance"] + 10.0)) < 1e-6


def test_wallet_debit_no_negative():
    # asegura saldo suficiente
    _post(
        "/wallet/credit",
        {"customer_id": CUST, "amount": 5.0},
        {"Idempotency-Key": "prep" + str(time.time())},
    )
    # intenta pasar saldo
    st, js = _post(
        "/wallet/debit",
        {"customer_id": CUST, "amount": 999999.0},
        {"Idempotency-Key": "bad" + str(time.time())},
    )
    assert st == 409 and "insufficient_funds" in js.get("detail", "")


def test_wallet_ledger_list():
    st, js = _get("/wallet/ledger", {"customer_id": CUST, "limit": 5})
    assert st == 200 and isinstance(js.get("entries"), list)
