#!/usr/bin/env bash
set -euo pipefail
BASE="http://127.0.0.1:8010"
h(){ curl -sS -H "Content-Type: application/json" "$@"; }

open=$(h -d '{"pos_id":1,"cashier_id":1,"opening_cash":0}' "$BASE/session/open")
sid=$(jq -r '.id' <<<"$open")

draft=$(h -d "{\"customer_id\":233366,\"session_id\":$sid,\"price_list_id\":1,\"items\":[{\"product_id\":1,\"qty\":1,\"unit_price\":129,\"price\":129}]}" "$BASE/pos/order/draft")
oid=$(jq -r '.order_id' <<<"$draft")

val=$(h -d "{\"code\":\"TEST10\",\"amount\":129.0,\"session_id\":$sid,\"order_id\":$oid}" "$BASE/pos/coupon/validate")
new_total=$(jq -r '.new_total' <<<"$val")

h -d "{\"session_id\":$sid,\"order_id\":$oid,\"splits\":[{\"method\":\"cash\",\"amount\":$new_total}],\"coupon_code\":\"TEST10\",\"customer_id\":233366}" "$BASE/pos/order/pay-discounted" >/dev/null

today=$(date -u +%F)
curl -sS "$BASE/reports/coupon/audit/range?start=$today&end=$today&mode=utc" | jq .
