"""Vision recognizer: status policy, request building and answer parsing.

The vision path has no two-pass agreement check, so it reuses only the common
tail (known language + dictionary) of the OCR policy. These tests pin both the
vision-specific rules and the fact that the OCR two-pass rules are unchanged.
The HTTP layer runs on an ``httpx.MockTransport``: no network, no real model.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Callable

import httpx
import pytest

from duosave import config, recognize, vision
from duosave.config import APP_CARD, APP_DUO
from duosave.patchfmt import MAX_PAIRS, MAX_TEXT
from duosave.recognize import Pair, Recognition


def _study_pair() -> list[Pair]:
    return [Pair(original="czas", translation="time", kind="word")]


def test_empty_pairs_on_other_app_is_skipped() -> None:
    rec = Recognition(app="other")
    assert recognize.vision_policy(rec) == ("skipped", "vision_no_pair")


def test_empty_pairs_on_study_app_is_review() -> None:
    rec = Recognition(app=APP_DUO)
    assert recognize.vision_policy(rec) == ("review", "vision_no_pair")


def test_study_app_with_pairs_is_review_app_screen() -> None:
    rec = Recognition(app=APP_DUO, pairs=_study_pair())
    assert recognize.vision_policy(rec) == ("review", "app_screen")


def test_unknown_language_is_review_language_unknown() -> None:
    rec = Recognition(app=APP_CARD, language=None, pairs=_study_pair())
    assert recognize.vision_policy(rec) == ("review", "language_unknown")


def test_dictionary_rejection_is_review_dictionary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recognize, "dict_ok", lambda text, language: False)
    rec = Recognition(app=APP_CARD, language="pl", pairs=_study_pair())
    assert recognize.vision_policy(rec) == ("review", "dictionary")


def test_known_language_and_dictionary_is_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recognize, "dict_ok", lambda text, language: True)
    rec = Recognition(app=APP_CARD, language="pl", pairs=_study_pair())
    assert recognize.vision_policy(rec) == ("auto", "")


def test_ocr_policy_keeps_its_two_pass_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disagree = Recognition(
        usable=True,
        app=APP_CARD,
        agreement=False,
        language="pl",
        pairs=_study_pair(),
    )
    assert recognize._policy(disagree, 2) == ("review", "pass_disagreement")

    monkeypatch.setattr(recognize, "dict_ok", lambda text, language: True)
    agree = Recognition(
        usable=True,
        app=APP_CARD,
        agreement=True,
        language="pl",
        pairs=_study_pair(),
    )
    assert recognize._policy(agree, 2) == ("auto", "")


# --------------------------------------------------------------- HTTP layer

KEY = "test-key"


def _pair(original: str = "Czy masz czas?", translation: str = "Do you have time?") -> dict:
    return {"original": original, "translation": translation, "kind": "sentence"}


def _payload(**overrides) -> str:
    answer = {
        "app": APP_CARD,
        "screen_type": "share_card",
        "language": "pl",
        "pairs": [_pair()],
    }
    answer.update(overrides)
    return json.dumps(answer)


def _answer(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _use_transport(monkeypatch: pytest.MonkeyPatch,
                   handler: Callable[[httpx.Request], httpx.Response]) -> None:
    monkeypatch.setattr(config, "VISION_API_KEY", KEY)
    monkeypatch.setattr(vision, "TRANSPORT", httpx.MockTransport(handler))


def _recognize() -> Recognition:
    return asyncio.run(vision.recognize_bytes(b"png-bytes", "image/png"))


def test_available_is_false_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "VISION_API_KEY", "")
    assert vision.available() is False


def test_available_is_true_with_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "VISION_API_KEY", KEY)
    assert vision.available() is True


def test_recognize_bytes_maps_a_valid_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recognize, "dict_ok", lambda text, language: True)
    monkeypatch.setattr(config, "VISION_BASE_URL", "https://openrouter.ai/api/v1")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _answer(_payload())

    _use_transport(monkeypatch, handler)

    rec = _recognize()

    assert rec.app == APP_CARD
    assert rec.screen_type == "share_card"
    assert rec.language == "pl"
    assert rec.pairs == [Pair("Czy masz czas?", "Do you have time?", "sentence")]
    assert rec.usable is True
    assert rec.agreement is None
    assert rec.language_source == "vision"
    assert (rec.status, rec.reason) == ("auto", "")
    assert isinstance(rec.elapsed, float)

    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert body["model"] == config.VISION_MODEL
    assert body["temperature"] == 0
    system = body["messages"][0]["content"]
    assert system == vision.prompt()
    assert "one JSON object and nothing else" in system
    assert "Never translate" in system
    content = body["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "Extract the vocabulary pairs from this frame."}
    assert content[1]["type"] == "image_url"
    encoded = base64.b64encode(b"png-bytes").decode("ascii")
    assert content[1]["image_url"]["url"] == f"data:image/png;base64,{encoded}"


@pytest.mark.parametrize(
    "base_url",
    ["https://openrouter.ai/api/v1/chat/completions", "https://openrouter.ai/api/v1/"],
)
def test_recognize_bytes_accepts_a_base_url_with_the_endpoint(
    monkeypatch: pytest.MonkeyPatch, base_url: str
) -> None:
    """The configured base URL may carry the endpoint path or a trailing slash."""
    monkeypatch.setattr(recognize, "dict_ok", lambda text, language: True)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return _answer(_payload())

    monkeypatch.setattr(config, "VISION_BASE_URL", base_url)
    _use_transport(monkeypatch, handler)

    _recognize()

    assert seen == ["https://openrouter.ai/api/v1/chat/completions"]


def test_recognize_bytes_strips_code_fences(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recognize, "dict_ok", lambda text, language: True)
    fenced = f"```json\n{_payload()}\n```"
    _use_transport(monkeypatch, lambda request: _answer(fenced))

    rec = _recognize()

    assert rec.app == APP_CARD
    assert rec.pairs == [Pair("Czy masz czas?", "Do you have time?", "sentence")]


def test_recognize_bytes_unknown_app_becomes_other(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_transport(monkeypatch, lambda request: _answer(_payload(app="instagram")))

    rec = _recognize()

    assert rec.app == "other"
    assert (rec.status, rec.reason) == ("review", "app_screen")


def test_recognize_bytes_language_outside_languages_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_transport(monkeypatch, lambda request: _answer(_payload(language="de")))

    rec = _recognize()

    assert rec.language is None
    assert (rec.status, rec.reason) == ("review", "language_unknown")


def test_recognize_bytes_truncates_pairs_and_text(monkeypatch: pytest.MonkeyPatch) -> None:
    long_text = "x" * (MAX_TEXT + 50)
    pairs = [_pair(original=long_text)]
    pairs += [
        _pair(original=f"original {index}", translation=f"translation {index}")
        for index in range(1, 12)
    ]
    _use_transport(monkeypatch, lambda request: _answer(_payload(pairs=pairs)))

    rec = _recognize()

    assert len(rec.pairs) == MAX_PAIRS == 10
    assert rec.pairs[0].original == long_text[:MAX_TEXT]
    assert rec.pairs[0].translation == "Do you have time?"


def test_recognize_bytes_empty_pairs_other_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_transport(monkeypatch, lambda request: _answer(_payload(app="other", pairs=[])))

    rec = _recognize()

    assert rec.app == "other"
    assert rec.pairs == []
    assert rec.usable is False
    assert (rec.status, rec.reason) == ("skipped", "vision_no_pair")


def test_recognize_bytes_empty_pairs_study_is_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_transport(monkeypatch, lambda request: _answer(_payload(app=APP_DUO, pairs=[])))

    rec = _recognize()

    assert rec.app == APP_DUO
    assert rec.usable is False
    assert (rec.status, rec.reason) == ("review", "vision_no_pair")


@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "http_401"), (402, "http_402"), (429, "http_429"), (500, "http_5xx")],
)
def test_recognize_bytes_reports_provider_status(
    monkeypatch: pytest.MonkeyPatch, status: int, reason: str
) -> None:
    _use_transport(monkeypatch, lambda request: httpx.Response(status, text="provider error"))

    with pytest.raises(vision.VisionUnavailable) as excinfo:
        _recognize()

    assert excinfo.value.reason == reason


def test_recognize_bytes_reports_the_provider_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The numeric status and the provider message survive for the journal."""
    _use_transport(monkeypatch, lambda request: httpx.Response(
        404, json={"error": {"message": "No endpoints found", "code": 404}}))

    with pytest.raises(vision.VisionUnavailable) as excinfo:
        _recognize()

    assert excinfo.value.reason == "http_5xx"
    assert excinfo.value.status == 404
    assert excinfo.value.detail == "No endpoints found"


def test_recognize_bytes_reports_a_non_json_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A login page instead of JSON still names its status; the text is collapsed."""
    _use_transport(monkeypatch, lambda request: httpx.Response(
        403, text="<html>\n  sign in\n</html>"))

    with pytest.raises(vision.VisionUnavailable) as excinfo:
        _recognize()

    assert excinfo.value.status == 403
    assert excinfo.value.detail == "<html> sign in </html>"


def test_recognize_bytes_reports_timeout_and_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("too slow", request=request)

    _use_transport(monkeypatch, timeout)
    with pytest.raises(vision.VisionUnavailable) as excinfo:
        _recognize()
    assert excinfo.value.reason == "timeout"

    def transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _use_transport(monkeypatch, transport)
    with pytest.raises(vision.VisionUnavailable) as excinfo:
        _recognize()
    assert excinfo.value.reason == "transport"


def test_recognize_bytes_reports_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_transport(monkeypatch, lambda request: httpx.Response(200, text="not json at all"))
    with pytest.raises(vision.VisionUnavailable) as excinfo:
        _recognize()
    assert excinfo.value.reason == "bad_json"

    _use_transport(monkeypatch, lambda request: _answer("no object here"))
    with pytest.raises(vision.VisionUnavailable) as excinfo:
        _recognize()
    assert excinfo.value.reason == "bad_json"


def test_recognize_bytes_reports_bad_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_transport(monkeypatch, lambda request: httpx.Response(200, json={"error": "no choices"}))
    with pytest.raises(vision.VisionUnavailable) as excinfo:
        _recognize()
    assert excinfo.value.reason == "bad_shape"

    _use_transport(monkeypatch, lambda request: _answer('{"pairs": "broken"}'))
    with pytest.raises(vision.VisionUnavailable) as excinfo:
        _recognize()
    assert excinfo.value.reason == "bad_shape"


def test_recognize_bytes_without_a_key_raises_no_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the provider must not be called without a key")

    monkeypatch.setattr(config, "VISION_API_KEY", "")
    monkeypatch.setattr(vision, "TRANSPORT", httpx.MockTransport(forbidden))

    with pytest.raises(vision.VisionUnavailable) as excinfo:
        _recognize()

    assert excinfo.value.reason == "no_token"
    assert excinfo.value.status is None
    assert excinfo.value.detail == ""
