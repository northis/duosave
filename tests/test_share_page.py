"""Share outcome page (`GET /share`) and the inactive-worker safety net (`POST /share`).

The page is plain static HTML wired by `app.js`: it reads the outcome from the URL and never
touches the database, so what is checked is the served page, the parameters and strings the
client depends on, and the redirect contract of the POST fallback whose body is never parsed.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parents[1] / "duosave" / "server" / "static"
I18N_KEYS = ("share_title", "share_counts", "share_open_card", "share_to_review",
             "share_to_search", "share_redirect", "share_sw_stale", "share_empty")
ERROR_KEYS = ("upload_err_csrf", "upload_err_too_large", "upload_err_too_large_no_limit",
              "upload_err_not_an_image", "upload_err_busy", "upload_err_generic")
SW_FALLBACK = "/share?error=sw"


def test_get_share_serves_the_page(client: TestClient) -> None:
    response = client.get("/share")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="share"' in response.text
    assert 'href="/"' in response.text
    assert 'href="/review"' in response.text


def test_share_page_reads_the_outcome_from_the_url() -> None:
    html = (STATIC / "share.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    assert "initSharePage()" in html
    assert 'id="share"' in html
    assert '["new", "review", "skip", "dup"]' in js
    assert 'shareCount(params, "card")' in js
    assert 'params.get("error")' in js
    assert "uploadErrorText({ error })" in js
    for key in I18N_KEYS + ERROR_KEYS:
        assert js.count(key + ":") >= 2, f"{key} is missing from one of the languages"


def test_share_page_opens_the_main_page_when_the_share_is_done() -> None:
    """The status stays visible for a moment, then the main page opens by itself.

    An error keeps the page in place (the inactive-worker case offers the upload panel
    there), so the redirect is scheduled only after the error check returns.
    """
    html = (STATIC / "share.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'id="share-redirect"' in html
    assert 'data-i18n="share_redirect"' in html
    assert "SHARE_REDIRECT_MS" in js
    assert 'location.replace("/")' in js
    assert "setTimeout(" in js
    assert js.index("if (error) return;") < js.index('location.replace("/")')


def test_post_share_redirects_to_the_sw_fallback(client: TestClient) -> None:
    response = client.post("/share", data={"images": ("shot.png", b"\x89PNG\r\n", "image/png")},
                           follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == SW_FALLBACK


def test_post_share_does_not_parse_the_body(client: TestClient) -> None:
    broken = client.post(
        "/share",
        content=b"--boundary\r\nContent-Disposition: form-data; name=\"images\"\r\n\r\n",
        headers={"Content-Type": "multipart/form-data; boundary=boundary"},
        follow_redirects=False,
    )
    bare = client.post("/share", content=b"not multipart at all", follow_redirects=False)

    assert broken.status_code == 303
    assert bare.status_code == 303
    assert broken.headers["location"] == SW_FALLBACK
    assert bare.headers["location"] == SW_FALLBACK


def test_post_share_is_not_gated(client: TestClient) -> None:
    response = client.post("/share", content=b"image", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == SW_FALLBACK
