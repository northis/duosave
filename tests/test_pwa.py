"""PWA shell: the web app manifest, the installable icons and the theme colour of the pages.

The icons are committed PNGs (see `tools/make_icons.py`), so what is checked here is what the
browser will actually fetch: the manifest type and members, the size and opacity of every
declared icon, and that each page points at them.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parents[1] / "duosave" / "server" / "static"
PAGES = ("index.html", "review.html", "admin.html")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
RGBA, RGB = 6, 2  # PNG colour types: with and without an alpha channel


def manifest() -> dict:
    return json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))


def icon_path(icon: dict) -> Path:
    return STATIC / icon["src"].removeprefix("/static/")


def png_header(path: Path) -> tuple[int, int, int]:
    """(width, height, colour type) straight from IHDR — no need to decode the image."""
    data = path.read_bytes()
    assert data[:8] == PNG_MAGIC, f"{path.name} is not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height, data[25]


def test_manifest_is_served_as_a_manifest(client: TestClient) -> None:
    response = client.get("/manifest.webmanifest")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")
    assert response.json()["name"] == "Duosave"


def test_manifest_has_what_installability_requires() -> None:
    data = manifest()
    any_purpose = {icon["sizes"] for icon in data["icons"] if icon["purpose"] == "any"}

    assert data["short_name"]
    assert data["start_url"] == "/"
    assert data["display"] == "standalone"
    assert data.get("prefer_related_applications", False) is False
    assert any_purpose >= {"192x192", "512x512"}


def test_every_declared_icon_exists_at_its_declared_size() -> None:
    for icon in manifest()["icons"]:
        width, height = (int(part) for part in icon["sizes"].split("x"))

        assert png_header(icon_path(icon))[:2] == (width, height)


def test_any_icons_are_transparent_and_maskable_is_not() -> None:
    """Android draws a transparent icon on a white circle: the maskable one must be opaque,
    while the `any` ones stay transparent like the favicon (no padding baked in)."""
    maskable = [icon for icon in manifest()["icons"] if icon["purpose"] == "maskable"]
    any_purpose = [icon for icon in manifest()["icons"] if icon["purpose"] == "any"]

    assert maskable and any_purpose
    for icon in maskable:
        assert png_header(icon_path(icon))[2] == RGB
    for icon in any_purpose:
        assert png_header(icon_path(icon))[2] == RGBA
    assert png_header(STATIC / "icons" / "apple-touch-icon-180.png") == (180, 180, RGB)


def test_icons_are_served(client: TestClient) -> None:
    response = client.get("/static/icons/maskable-512.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_every_page_points_at_the_pwa_assets() -> None:
    for page in PAGES:
        html = (STATIC / page).read_text(encoding="utf-8")

        assert '<link rel="manifest" href="/manifest.webmanifest">' in html
        assert '<meta name="theme-color" content="#f6f1e8">' in html
        assert '<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon-180.png">' in html


def test_app_js_keeps_the_theme_colour_in_sync() -> None:
    """The header toggles the theme, so the browser chrome around the app must follow it."""
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'meta[name="theme-color"]' in script
    assert "#16171b" in script  # style.css --bg of the dark theme
