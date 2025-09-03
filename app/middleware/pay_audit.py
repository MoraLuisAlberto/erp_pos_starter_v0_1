from __future__ import annotations

from datetime import datetime, timezone
import json
import threading

from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

# *** Unificar archivo de auditoría ***
# Usamos el MISMO archivo que define el módulo de cupones (fuente de verdad).
from app.routers.pos_coupons import _AUDIT_FILE as AUDIT_FILE

_LOCK = threading.Lock()


def _append_jsonl(obj: dict) -> None:
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False)
    with _LOCK:
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _dedup_exists(payment_id=None, key=None) -> bool:
    if not AUDIT_FILE.exists():
        return False
    try:
        with open(AUDIT_FILE, encoding="utf-8") as f:
            for ln in f:
                try:
                    ev = json.loads(ln)
                except Exception:
                    continue
                if ev.get("kind") != "paid":
                    continue
                if payment_id and ev.get("payment_id") == payment_id:
                    return True
                if key and ev.get("idempotency_key") == key:
                    return True
    except Exception:
        return False
    return False


class PayAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        try:
            path = request.url.path
            if path not in ("/pos/order/pay", "/pos/order/pay-discounted"):
                return response
            if response.status_code != 200:
                return response

            # Captura el body y reinyéctalo para no consumir el stream
            body_chunks = [section async for section in response.body_iterator]
            body_bytes = b"".join(body_chunks)
            response.body_iterator = iterate_in_threadpool(iter([body_bytes]))

            # Parse JSON
            data = {}
            try:
                data = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                return response

            order = data.get("order") or {}
            order_id = order.get("order_id") or data.get("order_id")
            payment_id = data.get("payment_id")
            amount = data.get("amount")
            base_total = order.get("subtotal") or order.get("total")
            # Si no viene "amount", intenta sumar splits (robustez extra)
            if amount is None:
                try:
                    splits = data.get("splits") or []
                    amount = sum(float(s.get("amount") or 0) for s in splits)
                except Exception:
                    amount = None

            key = request.headers.get("x-idempotency-key") or request.headers.get(
                "X-Idempotency-Key"
            )

            if not _dedup_exists(payment_id=payment_id, key=key):
                ev = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "kind": "paid",
                    "code": None,  # si luego tienes el código, puedes rellenarlo aquí
                    "customer_id": None,  # idem para cliente
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "idempotency_key": key,
                    "base_total": base_total,
                    "paid_total": amount,
                    "path": path,
                    "method": "auto",
                }
                _append_jsonl(ev)
        finally:
            return response


def install_pay_audit(app):
    app.add_middleware(PayAuditMiddleware)
