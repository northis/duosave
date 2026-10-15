"""Portuguese as the main language: the default filter, the chips, /api/languages, the prompt.

The site opens on the main course instead of "all languages"; the language lists start
with it and the vision request always asks the model to decide the studied language, so a
frame that cannot be classified reaches the review queue with a combobox to fix it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from duosave import config, vision

STATIC = Path(__file__).resolve().parents[1] / "duosave" / "server" / "static"


def test_portuguese_is_the_default_language() -> None:
    assert config.DEFAULT_LANGUAGE == "pt"
    assert config.LANGUAGES[0] == "pt"
    assert set(config.LANGUAGES) == {"pt", "pl", "es"}


def test_languages_endpoint_lists_the_main_course_first(client: TestClient) -> None:
    response = client.get("/api/languages")

    assert response.status_code == 200
    data = response.json()
    assert data["default"] == "pt"
    assert [item["code"] for item in data["languages"]] == list(config.LANGUAGES)
    assert data["languages"][0] == {"code": "pt", "name": "Portuguese"}
    assert data["languages"][1]["name"] == "Polish"
    assert data["languages"][2]["name"] == "Spanish"


def test_index_chips_start_with_portuguese_and_it_is_active() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    chips = html[html.index('id="lang-chips"'):html.index('id="app-chips"')]

    order = [value for value in ("pt", "pl", "es") if f'data-value="{value}"' in chips]
    assert order == ["pt", "pl", "es"]
    assert 'class="chip active" data-value="pt"' in chips
    assert 'class="chip active" data-value=""' not in chips


def test_app_js_defaults_to_the_same_language() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    assert f'const DEFAULT_LANG = "{config.DEFAULT_LANGUAGE}"' in js
    # an explicit lang= (including the empty one: "all languages") wins over the default
    assert 'p.has("lang")' in js


def test_review_combobox_is_built_from_the_api_and_sent_with_every_action() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'fetchJson("/api/languages")' in js
    assert "languageOptions" in js
    assert 'class="lang-select"' in js
    assert "pickedLanguage(" in js
    assert "JSON.stringify({ path, action, language })" in js
    assert 'JSON.stringify({ path, action: "edit", original, translation, language })' in js
    assert "loadLanguages()" in js


def test_vision_prompt_asks_the_model_to_decide_the_language() -> None:
    prompt = vision.prompt()

    assert 'language: "pt" | "pl" | "es"' in prompt
    assert "Always decide the studied language" in prompt
