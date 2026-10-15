"""Profiling middleware and versioned page assets."""

from __future__ import annotations

from fastapi.testclient import TestClient

from duosave import __version__


def test_api_responses_carry_server_timing(client: TestClient) -> None:
    response = client.get("/api/version")

    assert response.headers["server-timing"].startswith("app;dur=")
    assert response.headers["x-duosave-request"].isdigit()


def test_static_assets_are_revalidated(client: TestClient) -> None:
    response = client.get("/static/style.css")

    assert response.headers["cache-control"] == "no-cache"


def test_pages_link_versioned_assets(client: TestClient) -> None:
    html = client.get("/").text

    assert f'/static/style.css?v={__version__}"' in html
    assert f'/static/app.js?v={__version__}"' in html
