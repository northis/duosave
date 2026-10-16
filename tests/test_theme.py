"""Theme: the load-more button and the boot screen that paints before style.css arrives.

The pages are plain HTML with no build step, so what is checked here is what the browser gets:
the button has to set its own colour (a `button` keeps the user agent's `buttontext` otherwise,
which follows the operating system and ignores the app theme), every page has to apply the stored
theme before its first paint, and the four pages have to carry the same boot screen.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "duosave" / "server" / "static"
PAGES = ("index.html", "review.html", "admin.html", "share.html")
HEAD = re.compile(r"<head>(.*?)</head>", re.S)
INLINE = re.compile(r"<(script|style)>(.*?)</\1>", re.S)


def page(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def head(name: str) -> str:
    return HEAD.search(page(name)).group(1)


def inline_blocks(name: str) -> list[tuple[str, str]]:
    return INLINE.findall(head(name))


def css() -> str:
    return (STATIC / "style.css").read_text(encoding="utf-8")


def rule(selector: str) -> str:
    """The declaration block of one selector, as style.css writes it."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css())
    assert match, f"{selector} is not in style.css"
    return match.group(1)


def theme_backgrounds() -> tuple[str, str]:
    """(light, dark) --bg from style.css: the page, the boot screen and the splash share them."""
    light = re.search(r":root\s*\{[^}]*--bg:\s*([^;]+);", css())
    dark = re.search(r':root\[data-theme="dark"\]\s*\{[^}]*--bg:\s*([^;]+);', css())
    assert light and dark
    return light.group(1).strip(), dark.group(1).strip()


def boot_style() -> str:
    """The inline <style> of index.html: the boot screen, the same in every page."""
    blocks = [body for tag, body in inline_blocks("index.html") if tag == "style"]
    assert len(blocks) == 1
    return blocks[0]


def test_more_button_sets_its_own_colour() -> None:
    """A `button` does not inherit `color`: without it the label keeps the user agent's
    `buttontext` — black on the dark surface in a browser, light grey on a phone — instead of
    following the theme the rest of the page is drawn in."""
    assert "color: var(--text)" in rule(".more")


def test_more_button_answers_the_pointer() -> None:
    assert "var(--accent)" in rule(".more:hover")


def test_every_page_applies_the_theme_before_the_first_paint() -> None:
    """The theme is an attribute on <html> and the stylesheet is render-blocking: applying it
    from app.js (end of the body) leaves the first paint — the boot screen — in the light theme."""
    for name in PAGES:
        bootstrap = [body for tag, body in inline_blocks(name) if tag == "script" and "duosave_theme" in body]

        assert bootstrap, f"{name} does not read the stored theme in the head"
        assert "dataset.theme" in bootstrap[0]
        assert "prefers-color-scheme: dark" in bootstrap[0]
        assert head(name).index(bootstrap[0]) < head(name).index("/static/style.css")


def test_all_pages_carry_the_same_boot_screen() -> None:
    """It has to be inlined (it is the first frame, style.css is still on the wire), so the four
    copies are compared with each other: an edit in one page only shows up here."""
    expected = inline_blocks("index.html")

    assert [tag for tag, _ in expected] == ["script", "style"]
    for name in PAGES[1:]:
        assert inline_blocks(name) == expected, f"{name} differs from index.html"


def test_boot_screen_uses_the_page_backgrounds() -> None:
    light, dark = theme_backgrounds()
    style = boot_style()
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))

    assert f"background: {light}" in style
    assert f"background: {dark}" in style
    assert 'html[data-theme="dark"] #boot' in style
    # The OS splash is drawn by the system, which has no dark variant: it is dark on purpose,
    # so the launch does not start with a bright flash, and it is the same in both themes.
    assert manifest["background_color"] == dark


def test_boot_screen_shows_on_launch_and_not_on_a_navigation() -> None:
    """The launch screen belongs to the launch: a page opened inside a running tab (and not the
    share outcome, which the share sheet opens with the app cold) paints without it."""
    for name in PAGES:
        bootstrap = [body for tag, body in inline_blocks(name) if tag == "script" and "duosave_theme" in body][0]

        assert "sessionStorage" in bootstrap
        assert 'location.pathname === "/share"' in bootstrap
        assert 'dataset.boot = "skip"' in bootstrap
    assert 'html[data-boot="skip"] #boot { display: none; }' in boot_style()


def test_boot_screen_animates_and_waits_for_less_motion() -> None:
    style = boot_style()

    assert "@keyframes boot-pulse" in style
    assert "@keyframes boot-slide" in style
    assert "prefers-reduced-motion: reduce" in style


def test_boot_screen_is_the_first_thing_in_the_body() -> None:
    for name in PAGES:
        body = page(name).split("<body>", 1)[1].lstrip()

        assert body.startswith('<div id="boot"'), f"{name} does not open with the boot screen"
        assert 'data-i18n="loading"' in body  # the label follows the interface language
        assert 'aria-live="polite"' in body  # a reader is told the app is still loading


def test_app_js_fades_the_boot_screen_out() -> None:
    """Every page ends its first render in bootDone(); the watchdog covers a request that never
    answers, and the element is removed so it cannot swallow a click."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    admin = (STATIC / "admin.js").read_text(encoding="utf-8")

    assert "function bootDone()" in js
    assert 'document.getElementById("boot")' in js
    assert "BOOT_MAX_MS" in js
    assert js.count("bootDone()") >= 4  # the index, the review, the share page, the watchdog
    assert "bootDone()" in admin  # the admin page paints its loaders and drops the boot screen
