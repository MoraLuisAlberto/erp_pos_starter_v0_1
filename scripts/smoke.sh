#!/usr/bin/env bash
set -euo pipefail

BASE="${ERP_BASE_URL:-http://localhost:8010}"
COUPON="${TEST_COUPON:-TEST10}"
CUSTOMER="${TEST_CUSTOMER_ID:-$((RANDOM + 200000))}"

pp() { python -m json.tool || cat; }

# curl → BODY + STATUS (sin headers mezclados)
post_json() { # path json_payload  -> prints Status + body, exports BODY and CODE
  local path="$1"; shift
  local data="$1"; shift
  BODY="$(mktemp)"; CODE="$(curl -sS -o "$BODY" -w "%{http_code}" \
    -H 'Content-Type: application/json' -X POST "$BASE$path" --data "$data")"
  echo "Status: HTTP/1.1 $CODE"
  cat "$BODY" | pp
  echo
}

get_url() { # path -> prints Status + body, exports BODY and CODE
  local path="$1"; shift
  BODY="$(mktemp)"; CODE="$(curl -sS -o "$BODY" -w "%{http_code}" -X GET "$BASE$path")"
  echo "Status: HTTP/1.1 $CODE"
  cat "$BODY" | pp
  echo
}

# Helpers para leer campos JSON con Python (sin jq)
json_field() { # file key1[.key2[.key3...]]
  python - "$1" "$2" <<'PY'
import sys, json
f, path = sys.argv[1], sys.argv[2].split('.')
with open(f, encoding='utf-8') as fh:
    obj = json.load(fh)
for k in path:
    obj = obj[k]
print(obj)
PY
}

json_first_of() { # file keyA keyB -> imprime el primero que exista
  python - "$@" <<'PY'
import sys, json
f = sys.argv[1]
keys = sys.argv[2:]
with open(f, encoding='utf-8') as fh:
    obj = json.load(fh)
def get(o, k):
    cur = o
    for part in k.split('.'):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur
for k in keys:
    v = get(obj, k)
    if v is not None:
        print(v)
        sys.exit(0)
sys.exit(1)
PY
}

echo
echo "1) OPEN SESSION"
post_json "/session/open" '{"operator":"demo"}'
SESSION_ID="$(json_first_of "$BODY" "session_id" "id")" || true
: "${SESSION_ID:=1}"   # fallback suave

echo
echo "2) DRAFT"
# Un draft de $129.00 para mantener la prueba simple
post_json "/pos/order/draft" "{\"session_id\":${SESSION_ID},\"items\":[{\"product_id\":1,\"qty\":1,\"unit_price\":129.0}]}"
ORDER_ID="$(json_first_of "$BODY" "order_id" "order.order_id")"
SUBTOTAL="$(json_first_of "$BODY" "subtotal" "order.subtotal")"

echo
echo "3) VALIDATE"
# Tu API ahora exige 'amount' (no 'cart_total')
now="$(date -Iseconds -u)"
post_json "/pos/coupon/validate" "{\"code\":\"${COUPON}\",\"amount\":${SUBTOTAL},\"at\":\"${now}\"}"
# Si el esquema devuelve 'new_total' como string, lo usamos tal cual
NEW_TOTAL="$(json_first_of "$BODY" "new_total")" || NEW_TOTAL="$SUBTOTAL"

echo
echo "4) PAY-DISCOUNTED (coupon_code)"
# Construye el JSON con los valores parseados
PAY_JSON="$(printf '{"session_id":%s,"order_id":%s,"coupon_code":"%s","customer_id":%s,"amount":%s,"base_total":%s,"method":"cash"}' \
  "$SESSION_ID" "$ORDER_ID" "$COUPON" "$CUSTOMER" "$NEW_TOTAL" "$SUBTOTAL")"
post_json "/pos/order/pay-discounted" "$PAY_JSON"

echo
echo "5) AUDIT HOY (UTC)"
today="$(date -I)"
get_url "/reports/coupon/audit/range?start=${today}&end=${today}&mode=utc"

