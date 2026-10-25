from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

logger = logging.getLogger(__name__)


def normalize_request_id(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None

    candidate = raw_value.strip()
    if not candidate:
        return None

    if not _REQUEST_ID_PATTERN.match(candidate):
        return None

    return candidate


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming_request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
        request_id = incoming_request_id or uuid4().hex

        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "HTTP request processed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
