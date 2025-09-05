#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8010}"

# 1) abrir sesión
st=$(curl -sS -o /tmp/open.json -w "%{http_code}" -H "Content-Type: application/json" \
  -d '{"pos_id":1,"cashier_id":1,"opening_cash":0}' "$BASE/session/open")
[ "$st" = "200" ] || { echo "open session failed: $st"; cat /tmp/open.json; exit 1; }
sid=$(jq -r .id /tmp/open.json)

# 2) draft
st=$(curl -sS -o /tmp/draft.json -w "%{http_code}" -H "Content-Type: application/json" \
  -d '{"customer_id":233366,"session_id":'"$sid"',"price_list_id":1,"items":[{"product_id":1,"qty":1,"unit_price":129,"price":129}]}' \
  "$BASE/pos/order/draft")
[ "$st" = "200" ] || { echo "draft failed: $st"; cat /tmp/draft.json; exit 1; }
oid=$(jq -r .order_id /tmp/draft.json)

# 3) validate coupon
st=$(curl -sS -o /tmp/val.json -w "%{http_code}" -H "Content-Type: application/json" \
  -d '{"code":"TEST10","amount":129.0,"session_id":'"$sid"',"order_id":'"$oid"'}' \
  "$BASE/pos/coupon/validate")
[ "$st" = "200" ] || { echo "validate failed: $st"; cat /tmp/val.json; exit 1; }
new_total=$(jq -r .new_total /tmp/val.json)

# 4) pay-discounted
st=$(curl -sS -o /tmp/pay.json -w "%{http_code}" -H "Content-Type: application/json" \
  -d '{"session_id":'"$sid"',"order_id":'"$oid"',"splits":[{"method":"cash","amount":'"$new_total"'}],"coupon_code":"TEST10","customer_id":233366}' \
  "$BASE/pos/order/pay-discounted")
[ "$st" = "200" ] || { echo "pay failed: $st"; cat /tmp/pay.json; exit 1; }

echo "SMOKE OK ✓"
