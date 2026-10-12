"""Admin request guards: the local-listener check, CSRF checks, and the audit journal."""

from __future__ import annotations

import logging
import sys
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

CSRF_HEADER = "X-Duosave-Request"
ACTOR_HEADER = "Cf-Access-Authenticated-User-Email"

_AUDIT_LOGGER = "duosave.admin"
_DEFAULT_PORTS = {"http": "80", "https": "443"}
_LOCAL_ONLY_DETAIL = "admin is available only via the local listener"


class AdminError(Exception):
    """An expected admin failure, rendered as {"error": code, "detail": detail, **extra}."""

    def __init__(self, status: int, code: str, detail: str, **extra: object) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.extra = extra


def admin_error_handler(_request: Request, exc: AdminError) -> JSONResponse:
    return JSONResponse(
        {"error": exc.code, "detail": exc.detail, **exc.extra}, status_code=exc.status
    )


def is_local_admin(request: Request) -> bool:
    """True when the request arrived on the admin listener.

    The listener port comes from the socket that accepted the connection
    (`scope["server"]`), not from headers: `Host`/`X-Forwarded-*` are spoofable.
    """
    from .. import config

    port = config.ADMIN_PORT
    if not port:
        return False
    server = request.scope.get("server") or ()
    return len(server) == 2 and server[1] == port


def require_local(request: Request) -> None:
    """Admin routes are invisible on the public listener (404, not 403)."""
    if not is_local_admin(request):
        raise AdminError(404, "not_found", _LOCAL_ONLY_DETAIL)


def _strip_default_port(host: str) -> str:
    host = host.strip().lower()
    for port in _DEFAULT_PORTS.values():
        if host.endswith(":" + port):
            return host[: -(len(port) + 1)]
    return host


def _effective_host(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-host")
    host = forwarded.split(",")[0] if forwarded else (request.headers.get("host") or "")
    return _strip_default_port(host)


def _origin_host(origin: str | None) -> str | None:
    if not origin or origin == "null":
        return None
    try:
        parts = urlsplit(origin)
    except ValueError:
        return None
    if not parts.netloc:
        return None
    return _strip_default_port(parts.netloc)


def require_csrf(request: Request) -> None:
    """Custom header + Origin/Sec-Fetch-Site checks for every mutating admin request."""
    if request.headers.get(CSRF_HEADER) != "1":
        raise AdminError(403, "csrf", "missing header")
    origin = request.headers.get("origin")
    if origin is not None and _origin_host(origin) != _effective_host(request):
        raise AdminError(403, "csrf", "origin mismatch")
    site = request.headers.get("sec-fetch-site")
    if site is not None and site.lower() not in ("same-origin", "none"):
        raise AdminError(403, "csrf", "cross-site")


def forbid_cross_site(request: Request) -> None:
    """Downloads: a cross-site browser context must not trigger them."""
    site = request.headers.get("sec-fetch-site")
    if site is not None and site.lower() == "cross-site":
        raise AdminError(403, "csrf", "cross-site")


def actor(request: Request) -> str | None:
    """Journal identity: the verified CF Access email, printable ASCII only."""
    raw = request.headers.get(ACTOR_HEADER)
    if not raw:
        return None
    cleaned = "".join(ch for ch in raw if 32 <= ord(ch) < 127).strip()[:254]
    return cleaned or None


def audit(action: str, actor: str | None, **details: object) -> None:
    """Write one line to the admin journal (visible in `docker logs`)."""
    _ensure_audit_logger()
    extras = " ".join(f"{key}={value}" for key, value in details.items())
    logging.getLogger(_AUDIT_LOGGER).info("%s actor=%s %s", action, actor or "-", extras)


def _ensure_audit_logger() -> None:
    logger = logging.getLogger(_AUDIT_LOGGER)
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
