"""Request id, headers de seguridad, log de accesos y red de contención de errores."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

access_logger = logging.getLogger("api.access")
error_logger = logging.getLogger("api.error")

REQUEST_ID_HEADER = "X-Request-ID"
_DOCS_PREFIXES = ("/docs", "/redoc")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'"
HSTS = "max-age=31536000; includeSubDomains"


def internal_error_response(request_id: str | None) -> JSONResponse:
    """Respuesta genérica: nunca incluye el detalle del error (ni textos ORA-)."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, production: bool) -> None:
        super().__init__(app)
        self._production = production

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            error_logger.exception(
                "unhandled error",
                extra={"request_id": request_id, "path": request.url.path},
            )
            response = internal_error_response(request_id)

        self._apply_headers(request, response, request_id)
        access_logger.info(
            "request",
            extra={
                "request_id": request_id,
                "ip": request.client.host if request.client else None,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "user": getattr(request.state, "user", None),
            },
        )
        return response

    def _apply_headers(self, request: Request, response: Response, request_id: str) -> None:
        response.headers[REQUEST_ID_HEADER] = request_id
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        # Swagger UI / ReDoc (solo fuera de producción) cargan recursos externos.
        if not request.url.path.startswith(_DOCS_PREFIXES):
            response.headers.setdefault("Content-Security-Policy", API_CSP)
        if self._production:
            response.headers.setdefault("Strict-Transport-Security", HSTS)
