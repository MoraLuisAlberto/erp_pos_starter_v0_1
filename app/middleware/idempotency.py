import asyncio, time, json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class _IdemCache:
    def __init__(self, ttl=3600, max_entries=1024):
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

    async def set(self, key, value):
        async with self._lock:
            # prune expirados
            now = time.time()
            for k in list(self._store.keys()):
                if self._store[k]["exp"] < now:
                    self._store.pop(k, None)
            if len(self._store) >= self.max_entries:
                # expulsar cualquiera si se llenó
                self._store.pop(next(iter(self._store)))
            self._store[key] = value

_idem_cache = _IdemCache(ttl=3600, max_entries=2048)

class PayDiscountedIdempotency(BaseHTTPMiddleware):
    """
    Idempotencia para POST /pos/order/pay-discounted basada en Idempotency-Key.
    - Cachea solo respuestas 200 con JSON que tenga "payment_id".
    - En reintentos con la misma key, devuelve exactamente la misma respuesta.
    """
    async def dispatch(self, request, call_next):
        if request.method != "POST" or request.url.path != "/pos/order/pay-discounted":
            return await call_next(request)

        idem_key = (request.headers.get("Idempotency-Key")
                    or request.headers.get("IdempotencyKey"))
        if not idem_key:
            # sin key, flujo normal
            return await call_next(request)

        cache_key = f"{request.method}:{request.url.path}:{idem_key}"
        cached = await _idem_cache.get(cache_key)
        if cached:
            headers = dict(cached["headers"])
            headers["Idempotent-Replay"] = "true"
            return Response(
                content=cached["body"],
                status_code=cached["status"],
                media_type=cached["media_type"],
                headers=headers,
            )

        # primera vez: procesar y capturar body
        response = await call_next(request)

        body_bytes = b""
        async for chunk in response.body_iterator:
            body_bytes += chunk

        new_resp = Response(
            content=body_bytes,
            status_code=response.status_code,
            media_type=response.media_type,
            headers=dict(response.headers),
        )

        # cachear solo si 200 y contiene payment_id
        should_cache = new_resp.status_code == 200
        if should_cache:
            try:
                js = json.loads(body_bytes.decode("utf-8"))
                should_cache = "payment_id" in js
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

def install_idempotency(app):
    app.add_middleware(PayDiscountedIdempotency)
