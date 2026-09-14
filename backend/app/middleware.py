"""Request-scoped middleware."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.logging_setup import request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, expose it on the response, and log the outcome.

    An inbound X-Request-ID is honoured so a correlation id set by a gateway
    survives into our logs.

    **Unhandled exceptions are converted here rather than re-raised.** That is not
    cosmetic. Starlette's own error handler sits above the CORS middleware, so a
    500 it produces carries no ``Access-Control-Allow-Origin`` header. A browser on
    a different origin then blocks the response outright and ``fetch`` rejects with
    a network error — so a server-side fault presents in the UI as "the API cannot
    be reached", sending whoever is debugging it to check CORS settings and
    environment variables that were never wrong.

    This middleware runs *inside* CORS, so the response it returns gets the CORS
    headers on the way out and arrives as the 500 it actually is.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "request_id": request_id,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            # The exception text is deliberately not returned. This API serves
            # workers' pay records, and a database error can name tables and
            # columns. The request id is the handle: it is on this response and on
            # the logged traceback, so the two can be joined without publishing
            # anything about how the system is built.
            return JSONResponse(
                status_code=500,
                content={
                    "detail": (
                        "The server could not complete this request. Quote "
                        f"request id {request_id} when reporting it."
                    ),
                    "request_id": request_id,
                },
                headers={REQUEST_ID_HEADER: request_id},
            )
        finally:
            request_id_var.reset(token)

        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response
