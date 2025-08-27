import os, requests, datetime as dt

BASE = os.environ.get("ERP_POS_BASE", "http://127.0.0.1:8010")

def test_range_totals_match_csv_lines():
    today = dt.datetime.utcnow().date().isoformat()
    params = f"?start={today}&end={today}&mode=utc"

    r1 = requests.get(f"{BASE}/reports/coupon/audit/range{params}", timeout=10)
    assert r1.status_code == 200
    j1 = r1.json()
    total = j1["counts"]["total"]

    r2 = requests.get(f"{BASE}/reports/coupon/audit/export.csv{params}", timeout=10)
    assert r2.status_code == 200
    lines = [ln for ln in r2.text.splitlines() if ln.strip()]

    # CSV tiene encabezado: eventos = líneas - 1
    csv_events = max(0, len(lines) - 1)

    # Deben coincidir
    assert total == csv_events
