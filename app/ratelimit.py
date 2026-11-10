"""Rate limiting por IP: un límite global y límites adicionales por ruta (p. ej. el login).

Se usa la librería `limits` (el motor de slowapi) directamente: el SlowAPIMiddleware de
slowapi 0.1.10 no encuentra los handlers en FastAPI >= 0.13x (las rutas incluidas quedan
envueltas en `_IncludedRouter`) y deja pasar todos los requests sin limitar.

La IP es `scope["client"]`. Detrás del proxy, uvicorn con
`--proxy-headers --forwarded-allow-ips=127.0.0.1` la reemplaza por la IP real del cliente.
"""

import math
import time
from collections.abc import Mapping

from limits import RateLimitItem, parse
from limits.aio.strategies import MovingWindowRateLimiter
from limits.storage import storage_from_string
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        rate: str,
        storage_uri: str = "memory://",
        path_limits: Mapping[str, str] | None = None,
    ) -> None:
        self.app = app
        self._global = parse(rate)
        self._path_limits = {path: parse(value) for path, value in (path_limits or {}).items()}
        if not storage_uri.startswith("async+"):
            storage_uri = f"async+{storage_uri}"
        self._limiter = MovingWindowRateLimiter(storage_from_string(storage_uri))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        ip = client[0] if client else "unknown"
        checks: list[tuple[RateLimitItem, str]] = [(self._global, "global")]
        path_limit = self._path_limits.get(scope["path"])
        if path_limit is not None:
            checks.append((path_limit, scope["path"]))

        for limit, namespace in checks:
            if not await self._limiter.hit(limit, namespace, ip):
                await self._reject(limit, namespace, ip, scope, receive, send)
                return
        await self.app(scope, receive, send)

    async def _reject(
        self,
        limit: RateLimitItem,
        namespace: str,
        ip: str,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        stats = await self._limiter.get_window_stats(limit, namespace, ip)
        retry_after = max(1, math.ceil(stats.reset_time - time.time()))
        response = JSONResponse(
            status_code=429,
            content={"detail": "Too many requests"},
            headers={"Retry-After": str(retry_after)},
        )
        await response(scope, receive, send)
