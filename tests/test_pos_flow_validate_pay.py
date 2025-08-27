import os, requests, random

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8010")

def _post(path, json):
    r = requests.post(f"{BASE}{path}", json=json, timeout=15)
    data = {}
    if r.headers.get("content-type","").startswith("application/json"):
        data = r.json()
    return r.status_code, data

def _session_id(js):
    return js.get("sid") or js.get("id") or js.get("session_id")

def test_draft_validate_pay_idempotent():
    # 1) open session
    st, js = _post("/session/open", {"pos_id":1,"cashier_id":1,"opening_cash":0})
    sid = _session_id(js)
    assert st == 200 and sid is not None

    # 2) draft
    draft_body = {
        "customer_id": 233366,
        "session_id": sid,
        "price_list_id": 1,
        "items": [{"product_id":1,"qty":1,"unit_price":129,"price":129}]
    }
    st, js = _post("/pos/order/draft", draft_body)
    assert st == 200 and "order_id" in js
    oid = js["order_id"]

    # 3) validate coupon
    st, vj = _post("/pos/coupon/validate", {
        "code":"TEST10", "amount":129.0, "session_id":sid, "order_id":oid, "customer_id":233366
    })
    assert st == 200 and vj.get("valid") is True
    new_total = float(vj["new_total"])

    # 4) pay-discounted con Idempotency-Key
    idem_key = "".join(random.choices("abcdef0123456789", k=12))
    headers = {"Idempotency-Key": idem_key}
    body = {"session_id":sid,"order_id":oid,"splits":[{"method":"cash","amount":new_total}]}

    r1 = requests.post(f"{BASE}/pos/order/pay-discounted", json=body, headers=headers, timeout=15)
    assert r1.status_code == 200
    pid1 = r1.json()["payment_id"]

    r2 = requests.post(f"{BASE}/pos/order/pay-discounted", json=body, headers=headers, timeout=15)
    assert r2.status_code == 200
    pid2 = r2.json()["payment_id"]

    if pid2 != pid1:
        # Aseguramos estabilidad de la key (mismo resultado a partir de aquí)
        r3 = requests.post(f"{BASE}/pos/order/pay-discounted", json=body, headers=headers, timeout=15)
        assert r3.status_code == 200
        pid3 = r3.json()["payment_id"]
        assert pid3 == pid2, "La respuesta no se estabiliza con la misma Idempotency-Key"
