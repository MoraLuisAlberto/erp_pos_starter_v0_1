import os
import random
import datetime as dt
import requests

BASE = os.environ.get("ERP_BASE_URL", "http://localhost:8010")
COUPON = os.environ.get("TEST_COUPON", "TEST10")

def _post(path: str, payload: dict, idem: str | None = None) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    if idem:
        headers["x-idempotency-key"] = idem
    return requests.post(f"{BASE}{path}", headers=headers, json=payload, timeout=10)

def _get(path: str) -> requests.Response:
    return requests.get(f"{BASE}{path}", timeout=10)

def test_open_session_ok():
    r = _post("/session/open", {"operator": "demo"}, idem=f"pytest-open-{random.randint(1,1_000_000)}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "open"
    assert isinstance(data.get("id"), int)

def test_validate_coupon_ok():
    r = _post("/pos/coupon/validate", {
        "code": COUPON,
        "amount": 129.0,
        "at": dt.datetime.now(dt.timezone.utc).isoformat()
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("valid") is True
    assert data.get("code") == COUPON
    assert "new_total" in data

def test_pay_and_audit_ok():
    # 1) open session
    r = _post("/session/open", {"operator": "demo"}, idem=f"pytest-open-{random.randint(1,1_000_000)}")
    assert r.status_code == 200, r.text
    session_id = r.json().get("id")

    # 2) draft 129.00
    r = _post("/pos/order/draft", {"session_id": session_id, "items": [{"product_id": 1, "qty": 1, "unit_price": 129.0}]})
    assert r.status_code == 200, r.text
    order_id = r.json().get("order_id")
    subtotal = float(r.json().get("subtotal"))

    # 3) validate coupon → new_total
    r = _post("/pos/coupon/validate", {"code": COUPON, "amount": subtotal, "at": dt.datetime.now(dt.timezone.utc).isoformat()})
    assert r.status_code == 200, r.text
    new_total = float(r.json().get("new_total"))

    # 4) pay-discounted (evita usage_limit por cliente)
    customer_id = random.randint(200000, 999999)
    r = _post("/pos/order/pay-discounted", {
        "session_id": session_id,
        "order_id": order_id,
        "coupon_code": COUPON,
        "customer_id": customer_id,
        "amount": new_total,
        "base_total": subtotal,
        "method": "cash",
    }, idem=f"pytest-pay-{random.randint(1,1_000_000)}")
    assert r.status_code == 200, r.text
    pay = r.json()
    assert pay.get("coupon_code") == COUPON
    assert pay.get("code") == COUPON
    assert pay["order"]["status"] == "paid"

    # 5) audit hoy (UTC) incluye TEST10
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    r = _get(f"/reports/coupon/audit/range?start={today}&end={today}&mode=utc")
    assert r.status_code == 200, r.text
    rep = r.json()
    by_code = rep.get("by_code") or []
    found = next((b for b in by_code if b.get("code") == COUPON), None)
    assert found and int(found.get("paid", 0)) >= 1
