"""Favicon: the owl from the header (🦉) as the tab icon of every page."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parents[1] / "duosave" / "server" / "static"
PAGES = ("index.html", "review.html", "admin.html")
LINK = '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">'


def test_favicon_is_the_header_owl() -> None:
    svg = (STATIC / "favicon.svg").read_text(encoding="utf-8")

    assert "<svg" in svg and "viewBox" in svg
    assert "🦉" in svg
    assert "🦉" in (STATIC / "index.html").read_text(encoding="utf-8")  # the owl from <h1>


def test_every_page_links_the_favicon() -> None:
    for page in PAGES:
        assert LINK in (STATIC / page).read_text(encoding="utf-8")


def test_favicon_is_served(client: TestClient) -> None:
    response = client.get("/static/favicon.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "🦉" in response.text


def test_favicon_ico_redirects_to_the_owl(client: TestClient) -> None:
    response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.history[0].status_code == 307
    assert "🦉" in response.text
