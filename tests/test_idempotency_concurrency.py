import concurrent.futures as cf
import os
import random

import requests

BASE = os.environ.get("ERP_POS_BASE", "http://127.0.0.1:8010")


def _post(path, body, *, headers=None, timeout=10):
    r = requests.post(f"{BASE}{path}", json=body, headers=headers or {}, timeout=timeout)
    try:
        js = r.json()
    except Exception:
        js = {}
    return r.status_code, js


def _session_id(js):
    # tolerante a {"sid":...} o {"id":...}
    return js.get("sid") or js.get("id") or js.get("session_id")


def test_concurrent_pay_same_idempotency_key():
    # 1) sesión
    st, js = _post("/session/open", {"pos_id": 1, "cashier_id": 1, "opening_cash": 0})
    sid = _session_id(js)
    assert st == 200 and sid

    # 2) draft
    draft = {
        "customer_id": 233366,
        "session_id": sid,
        "price_list_id": 1,
        "items": [{"product_id": 1, "qty": 1, "unit_price": 129, "price": 129}],
    }
    st, js = _post("/pos/order/draft", draft)
    assert st == 200 and "order_id" in js
    oid = js["order_id"]

    # 3) validate (TEST10 10%)
    st, vj = _post(
        "/pos/coupon/validate",
        {
            "code": "TEST10",
            "amount": 129.0,
            "session_id": sid,
            "order_id": oid,
            "customer_id": 233366,
        },
    )
    assert st == 200 and vj.get("valid") is True
    new_total = float(vj["new_total"])

    # 4) dos pagos con la MISMA Idempotency-Key
    idem = "".join(random.choices("abcdef0123456789", k=16))
    headers = {"Idempotency-Key": idem}
    body = {"session_id": sid, "order_id": oid, "splits": [{"method": "cash", "amount": new_total}]}

    def do_pay():
        r = requests.post(
            f"{BASE}/pos/order/pay-discounted", json=body, headers=headers, timeout=15
        )
        assert r.status_code == 200
        return r.json()["payment_id"]

    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        pids = list(ex.map(lambda _: do_pay(), range(2)))

    # Ambas respuestas deben ser el mismo payment_id (replay idempotente)
    assert len(set(pids)) == 1
