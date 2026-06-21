"""Request/exception logging middleware with correlation ids (#1741).

Boundary instrumentation for the API layer: assigns or propagates an
``X-Request-ID``, stores it in the :mod:`scistudio.utils.log_setup` contextvar so
every downstream log record (and the per-run diagnostic log) is correlated,
logs one record per request (method, path, status, duration), and logs uncaught
exceptions at ERROR with a traceback before returning a 500 JSON body.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from scistudio.utils.log_setup import REQUEST_ID_HEADER, request_id_var

logger = logging.getLogger("scistudio.api.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with a correlation id; never swallow tracebacks."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        method = request.method
        path = request.url.path
        start = time.perf_counter()
        logger.debug("→ %s %s", method, path)
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error("✗ %s %s raised after %.1fms", method, path, duration_ms, exc_info=True)
            error = JSONResponse(
                {"detail": "Internal Server Error", "request_id": request_id},
                status_code=500,
            )
            error.headers[REQUEST_ID_HEADER] = request_id
            return error
        finally:
            request_id_var.reset(token)
        duration_ms = (time.perf_counter() - start) * 1000
        level = logging.WARNING if response.status_code >= 500 else logging.INFO
        logger.log(level, "%s %s %s %.1fms", method, path, response.status_code, duration_ms)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


__all__ = ["RequestLoggingMiddleware"]
