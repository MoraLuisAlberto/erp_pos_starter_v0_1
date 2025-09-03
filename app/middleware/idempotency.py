import asyncio
import json
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Endpoints soportados y la clave de éxito esperada en el JSON
ALLOW = {
    "/pos/order/pay-discounted": "payment_id",
    "/wallet/credit": "tx_id",
}


class _Cache:
    def __init__(self, ttl=3600, max_entries=2048):
        self.ttl = ttl
        self.max_entries = max_entries
        self._store = {}
        self._lock = asyncio.Lock()

    async def get(self, key):
        async with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            if item["exp"] < time.time():
                self._store.pop(key, None)
                return None
            return item

    async def set(self, key, val):
        async with self._lock:
            if len(self._store) >= self.max_entries:
                self._store.pop(next(iter(self._store)))
            self._store[key] = val


class _KeyedLocks:
    def __init__(self):
        self._locks = {}
        self._guard = asyncio.Lock()

    async def acquire(self, key):
        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
        await lock.acquire()
        return lock


def _drop_content_length(headers: dict) -> dict:
    # Quita cualquier Content-Length (casing-insensitive)
    return {k: v for k, v in headers.items() if k.lower() != "content-length"}


_idem_cache = _Cache(ttl=3600)
_keyed_locks = _KeyedLocks()


class PayDiscountedIdempotency(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method != "POST":
            return await call_next(request)

        path = request.url.path
        success_key = ALLOW.get(path)
        if not success_key:
            return await call_next(request)

        idem_key = request.headers.get("Idempotency-Key") or request.headers.get("IdempotencyKey")
        if not idem_key:
            return await call_next(request)

        cache_key = f"{request.method}:{path}:{idem_key}"

        # 1) Replay inmediato si está cacheado
        cached = await _idem_cache.get(cache_key)
        if cached:
            body_bytes = cached["body"]
            try:
                js = json.loads(body_bytes.decode("utf-8"))
                if isinstance(js, dict):
                    js.setdefault("replay", True)
                    body_bytes = json.dumps(js).encode("utf-8")
            except Exception:
                pass
            headers = _drop_content_length(dict(cached["headers"]))
            headers["Idempotent-Replay"] = "true"
            return Response(
                content=body_bytes,
                status_code=cached["status"],
                media_type=cached["media_type"],
                headers=headers,
            )

        # 2) Sección crítica por clave
        lock = await _keyed_locks.acquire(cache_key)
        try:
            cached = await _idem_cache.get(cache_key)
            if cached:
                body_bytes = cached["body"]
                try:
                    js = json.loads(body_bytes.decode("utf-8"))
                    if isinstance(js, dict):
                        js.setdefault("replay", True)
                        body_bytes = json.dumps(js).encode("utf-8")
                except Exception:
                    pass
                headers = _drop_content_length(dict(cached["headers"]))
                headers["Idempotent-Replay"] = "true"
                return Response(
                    content=body_bytes,
                    status_code=cached["status"],
                    media_type=cached["media_type"],
                    headers=headers,
                )

            # 3) Procesar y capturar body de la respuesta real
            response = await call_next(request)
            body_bytes = b""
            async for chunk in response.body_iterator:
                body_bytes += chunk

            headers = _drop_content_length(dict(response.headers))
            new_resp = Response(
                content=body_bytes,
                status_code=response.status_code,
                media_type=response.media_type,
                headers=headers,
            )

            # 4) Cachear solo si 200 y contiene la clave de éxito
            should_cache = response.status_code == 200
            if should_cache:
                try:
                    js = json.loads(body_bytes.decode("utf-8"))
                    should_cache = isinstance(js, dict) and (success_key in js)
                except Exception:
                    should_cache = False

            if should_cache:
                await _idem_cache.set(
                    cache_key,
                    {
                        "status": new_resp.status_code,
                        "headers": dict(new_resp.headers),
                        "media_type": new_resp.media_type,
                        "body": body_bytes,
                        "exp": time.time() + 3600,
                    },
                )

            return new_resp
        finally:
            lock.release()


def install_idempotency(app):
    app.add_middleware(PayDiscountedIdempotency)
