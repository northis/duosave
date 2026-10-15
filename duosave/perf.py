"""Profiling log: timed steps and HTTP requests, to see where a slow request hangs.

Lines go to stderr (`docker logs`) under the `duosave.perf` logger:

    perf start apply patch=p1                 <- a step began
    perf done  apply patch=p1 ms=1234          <- and finished (or "fail ... error=...")

A `start` without its `done` is the step that hangs. HTTP requests are logged the same
way by `PerfMiddleware`, which also sends `Server-Timing` so the browser console can show
the server share of each request.
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from itertools import count

LOGGER = "duosave.perf"
SLOW_MS = 1000
_ids = count(1)


def logger() -> logging.Logger:
    log = logging.getLogger(LOGGER)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


def _fields(details: dict) -> str:
    return " ".join(f"{key}={value}" for key, value in details.items())


@contextmanager
def timed(step: str, **details: object) -> Iterator[dict]:
    """Log the start and the end of a step with its duration; yields a dict for extra fields."""
    log = logger()
    extra: dict = {}
    log.info("perf start %s %s", step, _fields(details))
    started = time.perf_counter()
    try:
        yield extra
    except BaseException as exc:
        ms = round((time.perf_counter() - started) * 1000)
        log.warning("perf fail  %s %s ms=%d error=%s", step, _fields({**details, **extra}), ms,
                    type(exc).__name__)
        raise
    ms = round((time.perf_counter() - started) * 1000)
    level = logging.WARNING if ms >= SLOW_MS else logging.INFO
    log.log(level, "perf done  %s %s ms=%d", step, _fields({**details, **extra}), ms)


class PerfMiddleware:
    """Pure ASGI: logs API/admin requests, adds Server-Timing, keeps static files fresh.

    Static assets get `Cache-Control: no-cache` (revalidate by ETag) so a new release is
    picked up at once instead of a heuristically cached old `style.css`/`app.js`.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        static = path.startswith("/static/")
        logged = not static and not path.startswith(("/media/", "/src/"))
        request_id = next(_ids)
        method = scope.get("method", "")
        log = logger()
        started = time.perf_counter()
        status = {"code": 0}
        if logged:
            log.info("http start #%d %s %s", request_id, method, path)

        async def wrapped(message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                ms = (time.perf_counter() - started) * 1000
                headers = list(message.get("headers", []))
                headers.append((b"server-timing", f"app;dur={ms:.0f}".encode()))
                headers.append((b"x-duosave-request", str(request_id).encode()))
                if static:
                    headers = [h for h in headers if h[0].lower() != b"cache-control"]
                    headers.append((b"cache-control", b"no-cache"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, wrapped)
        finally:
            if logged:
                ms = round((time.perf_counter() - started) * 1000)
                level = logging.WARNING if ms >= SLOW_MS or status["code"] >= 500 else logging.INFO
                log.log(level, "http done  #%d %s %s status=%d ms=%d",
                        request_id, method, path, status["code"], ms)
