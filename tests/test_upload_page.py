"""Upload panel on the cards and review pages: the markup, the client and its strings.

The panel is plain static HTML wired by `app.js` (no build step), so what is checked here is
the contract the browser sees: the toggle button, the drop zone with its file input, the live
result list, the sequential raw-body upload and the RU/EN strings behind every visible line.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "duosave" / "server" / "static"
PAGES = ("index.html", "review.html")
I18N_KEYS = (
    "upload_btn", "upload_hint", "upload_busy", "upload_card", "upload_dup",
    "upload_review", "upload_open", "upload_err_csrf", "upload_err_too_large",
    "upload_err_not_an_image", "upload_err_busy", "upload_err_generic",
)


def test_index_and_review_have_the_upload_panel() -> None:
    for name in PAGES:
        html = (STATIC / name).read_text(encoding="utf-8")
        button = re.search(r'<button[^>]*id="upload-btn"[^>]*>', html)
        file_input = re.search(r'<input[^>]*type="file"[^>]*>', html)
        results = re.search(r'<div[^>]*id="upload-results"[^>]*>', html)

        assert button and "aria-expanded" in button.group(0), name
        assert 'id="upload-panel"' in html, name
        assert 'id="drop-zone"' in html, name
        assert file_input and "multiple" in file_input.group(0), name
        assert file_input and 'accept="image/*"' in file_input.group(0), name
        assert re.search(r'<label[^>]*for="upload-input"', html), name
        assert results and 'aria-live="polite"' in results.group(0), name


def test_app_js_sends_files_one_by_one() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'fetch("/api/upload"' in js
    assert '"X-Duosave-Request"' in js
    assert "for (const file of files) await " in js


def test_upload_button_uses_a_theme_aware_arrow() -> None:
    """The ⬆ glyph renders dark-on-dark in the dark theme: an SVG with currentColor follows."""
    for name in PAGES + ("share.html",):
        html = (STATIC / name).read_text(encoding="utf-8")
        start = html.index('id="upload-btn"')
        button = html[start:html.index("</button>", start)]

        assert "svg" in button, name
        assert 'stroke="currentColor"' in button, name


def test_upload_strings_are_i18n() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    for key in I18N_KEYS:
        assert js.count(key + ":") >= 2, f"{key} is missing from one of the languages"


def test_style_has_the_drop_zone() -> None:
    css = (STATIC / "style.css").read_text(encoding="utf-8")

    assert ".drop-zone" in css
    assert ".drop-zone.dragover" in css
    assert ".upload-row" in css
