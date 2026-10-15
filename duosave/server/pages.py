"""HTML pages with versioned asset URLs, so a new release never runs on a cached old CSS/JS."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.responses import HTMLResponse

from .. import __version__

STATIC = Path(__file__).resolve().parent / "static"
_ASSET_RE = re.compile(r'(/static/[\w.-]+\.(?:css|js))"')


def page(name: str) -> HTMLResponse:
    """The static page with `?v=<version>` appended to its stylesheet and script URLs."""
    html = (STATIC / name).read_text(encoding="utf-8")
    html = _ASSET_RE.sub(rf'\1?v={__version__}"', html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
