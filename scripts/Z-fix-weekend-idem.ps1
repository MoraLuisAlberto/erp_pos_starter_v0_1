$ErrorActionPreference = "Stop"

# Rutas
$idemPath   = "app\middleware\idempotency.py"
$mainPath   = "app\main.py"
$couponPath = "app\routers\coupon.py"

# Asegurar carpeta del middleware
New-Item -ItemType Directory -Force -Path (Split-Path $idemPath -Parent) | Out-Null

# 1) Escribir/actualizar el middleware de idempotencia (con lock por clave)
$py = @'
import asyncio, time, json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

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

_idem_cache = _Cache(ttl=3600)
_keyed_locks = _KeyedLocks()

class PayDiscountedIdempotency(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method != "POST" or request.url.path != "/pos/order/pay-discounted":
            return await call_next(request)

        idem_key = request.headers.get("Idempotency-Key") or request.headers.get("IdempotencyKey")
        if not idem_key:
            return await call_next(request)

        cache_key = f"{request.method}:{request.url.path}:{idem_key}"

        # Replay inmediato si ya estaba en caché
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

        # Sección crítica por clave
        lock = await _keyed_locks.acquire(cache_key)
        try:
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

            # Procesar y capturar body
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

            # Cachear solo 200 con "payment_id"
            should_cache = response.status_code == 200
            if should_cache:
                try:
                    js = json.loads(body_bytes.decode("utf-8"))
                    should_cache = "payment_id" in js
                except Exception:
                    should_cache = False

            if should_cache:
                await _idem_cache.set(cache_key, {
                    "status": new_resp.status_code,
                    "headers": dict(new_resp.headers),
                    "media_type": new_resp.media_type,
                    "body": body_bytes,
                    "exp": time.time() + 3600,
                })

            return new_resp
        finally:
            lock.release()

def install_idempotency(app):
    app.add_middleware(PayDiscountedIdempotency)
