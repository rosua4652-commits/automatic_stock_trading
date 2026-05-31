"""HTTP 요청 로그 — POST 버튼·처리 시간."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.aidi_log import action_label_for_path, log_action


class AidiActionLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        label = action_label_for_path(request.url.path, request.method)
        if not label:
            return await call_next(request)

        t0 = time.perf_counter()
        log_action(label, "처리 중…")
        response = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000
        ok = 200 <= response.status_code < 300
        log_action(
            label,
            f"HTTP {response.status_code}",
            ok=ok,
            ms=ms,
        )
        return response
