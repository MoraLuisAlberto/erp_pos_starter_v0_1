import os

import requests

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8010")


def test_health_returns_200():
    r = requests.get(f"{BASE}/health", timeout=10)
    assert r.status_code == 200
