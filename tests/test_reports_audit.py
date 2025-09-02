import datetime as dt
import os

import requests

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8010")


def _post(path, json):
    r = requests.post(f"{BASE}{path}", json=json, timeout=15)
    return r.status_code, r.json()


def _session_id(js):
    return js.get("sid") or js.get("id") or js.get("session_id")


def test_audit_range_after_paid():
    # reset (si existe)
    requests.post(
        f"{BASE}/pos/coupon/dev/reset-usage",
        json={"code": "TEST10", "customer_id": 233366},
        timeout=10,
    )

    st, js = _post("/session/open", {"pos_id": 1, "cashier_id": 1, "opening_cash": 0})
    sid = _session_id(js)
    assert st == 200 and sid is not None

    st, js = _post(
        "/pos/order/draft",
        {
            "customer_id": 233366,
            "session_id": sid,
            "price_list_id": 1,
            "items": [{"product_id": 1, "qty": 1, "unit_price": 129, "price": 129}],
        },
    )
    oid = js["order_id"]
    assert st == 200

    st, vj = _post(
        "/pos/coupon/validate",
        {"code": "TEST10", "amount": 129.0, "session_id": sid, "order_id": oid},
    )
    assert st == 200 and vj["valid"] is True
    new_total = float(vj["new_total"])

    st, pj = _post(
        "/pos/order/pay-discounted",
        {"session_id": sid, "order_id": oid, "splits": [{"method": "cash", "amount": new_total}]},
    )
    assert st == 200 and pj["order"]["status"] == "paid"

    today = dt.datetime.now(dt.UTC).date().isoformat()
    r = requests.get(
        f"{BASE}/reports/coupon/audit/range",
        params={"start": today, "end": today, "mode": "utc"},
        timeout=10,
    )
    assert r.status_code == 200
    rep = r.json()
    assert rep.get("file_exists") is True
    assert rep.get("counts", {}).get("by_kind", {}).get("paid", 0) >= 1
