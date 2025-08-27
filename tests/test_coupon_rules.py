import os, requests, datetime as dt, time

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8010")

def _post(path, json):
    r = requests.post(f"{BASE}{path}", json=json, timeout=15)
    return r.status_code, r.json()

def _iso_at(year, month, day, hour=12, minute=0):
    return dt.datetime(year, month, day, hour, minute, 0).isoformat()

def _next_weekday(target_weekday):  # Mon=0 ... Sun=6
    today = dt.date.today()
    delta = (target_weekday - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + dt.timedelta(days=delta)

def test_coupon_rules_matrix():
    # TEST10
    st, js = _post("/pos/coupon/validate", {"code":"TEST10","amount":129})
    assert st == 200 and js["valid"] is True and float(js["new_total"]) == 116.10

    # SAVE50 ok >=200
    st, js = _post("/pos/coupon/validate", {"code":"SAVE50","amount":220})
    assert st == 200 and js["valid"] is True and float(js["new_total"]) == 170.0

    # SAVE50 fail <200
    st, js = _post("/pos/coupon/validate", {"code":"SAVE50","amount":129})
    assert st == 200 and js["valid"] is False and js["reason"] in ("min_amount_not_met",)

    # NITE20 ok a las 20:00
    at_ok = _iso_at(2025,8,25,20,0)
    st, js = _post("/pos/coupon/validate", {"code":"NITE20","amount":129,"at":at_ok})
    assert st == 200 and js["valid"] is True

    # NITE20 fail a las 10:00
    at_bad = _iso_at(2025,8,25,10,0)
    st, js = _post("/pos/coupon/validate", {"code":"NITE20","amount":129,"at":at_bad})
    assert st == 200 and js["valid"] is False and js["reason"] in ("time_window_not_met",)

    # WEEKEND15 sábado OK, lunes NO (usando 'at' para robustez)
    next_sat = _next_weekday(5)   # 5 = Saturday
    next_mon = _next_weekday(0)   # 0 = Monday
    sat_at = dt.datetime.combine(next_sat, dt.time(12,0)).isoformat()
    mon_at = dt.datetime.combine(next_mon, dt.time(12,0)).isoformat()

    st, js = _post("/pos/coupon/validate", {"code":"WEEKEND15","amount":129,"at":sat_at})
    assert st == 200 and js["valid"] is True

    st, js = _post("/pos/coupon/validate", {"code":"WEEKEND15","amount":129,"at":mon_at})
    assert st == 200 and js["valid"] is False and js["reason"] in ("weekday_not_allowed",)
