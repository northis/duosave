"""Maintenance page, local-listener gating and the navigation link."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parents[1] / "duosave" / "server" / "static"
LOCAL_ONLY = "admin is available only via the local listener"


def test_admin_page_served_on_local_listener(admin_client: TestClient) -> None:
    response = admin_client.get("/admin")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="admin"' in response.text


def test_admin_page_hidden_on_public_listener(client: TestClient) -> None:
    response = client.get("/admin")

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "detail": LOCAL_ONLY}


def test_admin_api_hidden_on_public_listener(client: TestClient) -> None:
    # The gate sits on the whole router, so routes added in later tasks are covered too.
    from duosave.server import admin, security

    assert any(dep.dependency is security.require_local for dep in admin.router.dependencies)
    assert client.get("/api/admin/backup", params={"kind": "db"}).status_code == 404
    assert client.post("/api/admin/patches").status_code == 404


def test_local_check_runs_before_csrf(client: TestClient) -> None:
    response = client.post("/api/admin/patches", headers={"X-Duosave-Request": "1"})

    assert response.status_code == 404


def test_session_reports_the_listener(admin_client: TestClient, client: TestClient) -> None:
    local = admin_client.get("/api/session")
    public = client.get("/api/session")

    assert local.status_code == 200
    assert local.json() == {"local_admin": True}
    assert local.headers["cache-control"] == "no-store"
    assert public.json() == {"local_admin": False}


def test_nav_link_is_hidden_by_default() -> None:
    for name in ("index.html", "review.html"):
        html = (STATIC / name).read_text(encoding="utf-8")

        assert 'id="nav-admin"' in html
        assert 'href="/admin"' in html
        assert 'data-i18n="nav_admin"' in html
        assert "hidden" in html


def test_admin_page_marks_nav_active_and_loads_scripts() -> None:
    html = (STATIC / "admin.html").read_text(encoding="utf-8")

    assert 'href="/admin" class="active"' in html
    assert html.index("/static/app.js") < html.index("/static/admin.js")
    assert html.index("/static/admin.js") < html.index("initAdminPage()")


def test_app_js_loads_the_session() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    assert "loadSession" in js
    assert js.count("nav_admin:") == 2


def test_admin_js_registers_sections() -> None:
    js = (STATIC / "admin.js").read_text(encoding="utf-8")

    assert "ADMIN_SECTIONS" in js
    assert "function initAdminPage" in js
    assert "X-Duosave-Request" in js


def test_admin_panels_are_wired() -> None:
    html = (STATIC / "admin.html").read_text(encoding="utf-8")
    js = (STATIC / "admin.js").read_text(encoding="utf-8")

    for panel in ("patch-body", "backup-body", "cards-body"):
        assert f'id="{panel}"' in html
    assert "patchSection" in js
    assert "backupSection" in js
    assert "cardsSection" in js
    assert "/api/admin/known-hashes" in js
    assert "/api/admin/patches" in js


def test_admin_cards_panel_deletes_with_a_confirmation() -> None:
    """The delete panel is a search over the cards and one destructive action per row."""
    html = (STATIC / "admin.html").read_text(encoding="utf-8")
    js = (STATIC / "admin.js").read_text(encoding="utf-8")

    assert 'id="cards-panel"' in html
    assert 'data-i18n="adm_cards"' in html
    assert '"/api/admin/cards?limit=20&q="' in js
    assert 'method: "DELETE"' in js
    assert "window.confirm" in js
    for key in ("adm_cards", "cd_ph", "cd_search", "cd_delete", "cd_confirm", "cd_deleted",
                "cd_hint", "cd_found", "cd_col_card", "cd_col_app"):
        assert js.count(key + ":") >= 2, f"{key} is missing from one of the languages"


def test_admin_cards_panel_changes_the_language() -> None:
    """A language picker in the row: a fix instead of a removal when the label is wrong."""
    js = (STATIC / "admin.js").read_text(encoding="utf-8")

    assert "cardsSection.changeLanguage" in js
    assert "cardLanguageOptions" in js
    assert 'method: "PATCH"' in js
    assert '"/api/admin/cards/" + cardId' in js
    assert "report.merged_into" in js
    for key in ("cd_col_lang", "cd_lang_changed", "cd_lang_merged"):
        assert js.count(key + ":") >= 2, f"{key} is missing from one of the languages"


def test_admin_patch_picker_is_a_themed_button() -> None:
    """The native file input is ugly (dark on dark): a label styled like the buttons."""
    js = (STATIC / "admin.js").read_text(encoding="utf-8")

    assert 'for="patch-file"' in js
    assert 'class="btn upload-pick"' in js
    assert 'type="file" accept=".zip" multiple hidden' in js
    assert js.count("pt_pick:") == 2


def test_admin_panels_show_a_loader_while_loading() -> None:
    """The backup estimate and the patch list arrive asynchronously: a spinner instead
    of an empty panel while they load."""
    js = (STATIC / "admin.js").read_text(encoding="utf-8")
    css = (STATIC / "style.css").read_text(encoding="utf-8")

    assert ".loader" in css
    assert 'class="loader"' in js
    assert js.count('t("loading")') >= 3  # patch, backup and cards sections


def test_admin_page_has_no_update_panel() -> None:
    """2.3 removed the self-update daemon: the page has no update controls any more."""
    html = (STATIC / "admin.html").read_text(encoding="utf-8")
    js = (STATIC / "admin.js").read_text(encoding="utf-8")

    assert "update-body" not in html
    assert "updateSection" not in js
    assert "/api/admin/update" not in js
