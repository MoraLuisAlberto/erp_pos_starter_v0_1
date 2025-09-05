#!/usr/bin/env bash
set -euo pipefail

# Requiere: curl, jq
command -v jq >/dev/null 2>&1 || { echo "Necesitas jq (sudo apt-get install -y jq)"; exit 1; }

BASE="${BASE:-http://127.0.0.1:8010}"

req() { # req <json> <outfile> <url>  -> imprime solo status code
  curl -sS -o "$2" -w "%{http_code}" -H 'Content-Type: application/json' -d "$1" "$3"
}

# 1) abrir sesión
st=$(req '{"pos_id":1,"cashier_id":1,"opening_cash":0}' /tmp/open.json "$BASE/session/open")
[ "$st" = "200" ] || { echo "open session failed: $st"; cat /tmp/open.json; exit 1; }
sid=$(jq -r .id /tmp/open.json)

# 2) draft
st=$(req "{\"customer_id\":233366,\"session_id\":$sid,\"price_list_id\":1,\"items\":[{\"product_id\":1,\"qty\":1,\"unit_price\":129,\"price\":129}]}" /tmp/draft.json "$BASE/pos/order/draft")
[ "$st" = "200" ] || { echo "draft failed: $st"; cat /tmp/draft.json; exit 1; }
oid=$(jq -r .order_id /tmp/draft.json)

# 3) validate coupon
st=$(req "{\"code\":\"TEST10\",\"amount\":129.0,\"session_id\":$sid,\"order_id\":$oid}" /tmp/val.json "$BASE/pos/coupon/validate")
[ "$st" = "200" ] || { echo "validate failed: $st"; cat /tmp/val.json; exit 1; }
new_total=$(jq -r .new_total /tmp/val.json)

# 4) pay-discounted
st=$(req "{\"session_id\":$sid,\"order_id\":$oid,\"splits\":[{\"method\":\"cash\",\"amount\":$new_total}],\"coupon_code\":\"TEST10\",\"customer_id\":233366}" /tmp/pay.json "$BASE/pos/order/pay-discounted")
[ "$st" = "200" ] || { echo "pay failed: $st"; cat /tmp/pay.json; exit 1; }

# 5) reporte (opcional, imprime JSON bonito)
today=$(date -u +%F)
curl -sS "$BASE/reports/coupon/audit/range?start=$today&end=$today&mode=utc" | jq .

echo "SMOKE OK ✓"
