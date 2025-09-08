import datetime as dt
import os

import pytest
import requests

BASE = os.environ.get("ERP_POS_BASE", "http://127.0.0.1:8010")


def _post(path, body, *, headers=None, timeout=10):
    r = requests.post(f"{BASE}{path}", json=body, headers=headers or {}, timeout=timeout)
    try:
        js = r.json()
    except Exception:
        js = {}
    return r.status_code, js


def test_save50_threshold_and_decimals():
    # Umbral exacto 200 -> válido, total 150.00
    st, js = _post("/pos/coupon/validate", {"code": "SAVE50", "amount": 200})
    assert st == 200 and js["valid"] is True and float(js["new_total"]) == 150.0

    # Decimales: 200.01 -> 150.01 (descuento monto fijo 50)
    st, js = _post("/pos/coupon/validate", {"code": "SAVE50", "amount": 200.01})
    assert st == 200 and js["valid"] is True and abs(float(js["new_total"]) - 150.01) < 1e-6


def test_time_windows_extra_edges():
    # NITE20 solo de noche: 07:59 debe fallar
    at_bad = dt.datetime(2025, 8, 25, 7, 59, 0).isoformat()
    st, js = _post("/pos/coupon/validate", {"code": "NITE20", "amount": 129, "at": at_bad})
    assert st == 200 and js["valid"] is False and js["reason"] in ("time_window_not_met",)

    # WEEKEND15: domingo OK
    st, js = _post("/pos/coupon/validate", {"code": "WEEKEND15", "amount": 129, "weekday": "sun"})
    assert st == 200 and js["valid"] is True


def test_amount_zero_or_negative_rejected():
    st, js = _post("/pos/coupon/validate", {"code": "TEST10", "amount": 0})
    assert st == 422 or (st == 200 and js.get("valid") is False)

    st, js = _post("/pos/coupon/validate", {"code": "TEST10", "amount": -1})
    assert st == 422 or (st == 200 and js.get("valid") is False)
