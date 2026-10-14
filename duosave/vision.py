"""Vision recognition via an OpenAI-compatible chat completions API.

The only module that knows about the external provider: it builds the request
from raw image bytes, parses the model answer and maps it onto the existing
``Recognition`` shape, so storing a result stays shared with the OCR path.
Any failure raises ``VisionUnavailable`` with a reason from the error taxonomy;
callers fall back to local OCR.
"""

from __future__ import annotations

import base64
import json
import time

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from . import config, recognize
from .config import APP_CARD, APP_DROPS, APP_DUO, LANGUAGES
from .patchfmt import MAX_PAIRS, MAX_TEXT
from .recognize import Pair, Recognition

# Test seam: the tests replace this with an httpx.MockTransport.
TRANSPORT: httpx.AsyncBaseTransport | None = None

_STATUS_REASONS = {401: "http_401", 402: "http_402", 429: "http_429"}

# The chat completions path and the longest provider message that reaches the journal.
_ENDPOINT = "/chat/completions"
_DETAIL_LIMIT = 200

_SYSTEM_PROMPT = """You extract vocabulary pairs from language-learning screenshots.
Answer with one JSON object and nothing else — no markdown, no commentary.
Keys:
  app: "duolingo_card" | "duolingo_app" | "drops" | "other"
  screen_type: short snake_case label of the screen, or null
  language: "pl" | "es" | "pt" — the language being studied, or null
  pairs: array of {"original": str, "translation": str, "kind": "sentence" | "word"}
Rules:
  - original is the text in the studied language exactly as it appears on screen;
    translation is the English text exactly as it appears on screen.
  - Copy what is on screen. Never translate, complete or invent a side yourself: if the
    English side is not visible, leave that pair out and return an empty pairs array.
  - At most 10 pairs; prefer the pair the screen is about.
  - Chats, leaderboards, shops, settings, streak screens and banks are not vocabulary
    screens: return [] and set app to "other". A lesson, review or story screen with no
    visible English side keeps its real app value and also returns [].
  - If the studied language is not pl, es or pt, still fill the other keys and set
    language to null.
  - duolingo_card = square share card with a flag, one phrase and its translation;
    duolingo_app = Duolingo app screenshot; drops = Drops app screenshot."""


class VisionUnavailable(Exception):
    """Vision path cannot run; callers fall back to local OCR.

    ``status`` is the provider's HTTP status when there was an answer, and
    ``detail`` is its short message: both exist for the journal only.
    """

    def __init__(self, reason: str, status: int | None = None, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.detail = detail


class AnswerPair(BaseModel):
    """One vocabulary pair as returned by the model."""

    model_config = ConfigDict(extra="ignore")

    original: str
    translation: str
    kind: str = "sentence"

    @field_validator("original", "translation", mode="before")
    @classmethod
    def _truncate(cls, value: object) -> object:
        return value[:MAX_TEXT] if isinstance(value, str) else value


class Answer(BaseModel):
    """Parsed model answer; unknown keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    app: str | None = None
    screen_type: str | None = None
    language: str | None = None
    pairs: list[AnswerPair] = []

    @field_validator("screen_type", mode="before")
    @classmethod
    def _truncate_screen_type(cls, value: object) -> object:
        return value[:MAX_TEXT] if isinstance(value, str) else value


def available() -> bool:
    """Whether a vision key is configured (read at call time)."""
    return bool(config.VISION_API_KEY)


def prompt() -> str:
    """System prompt: one JSON object, copy what is on screen, never translate."""
    return _SYSTEM_PROMPT


def build_payload(data: bytes, media_type: str) -> dict:
    """Chat completions body: system prompt plus the frame as a base64 data URL."""
    encoded = base64.b64encode(data).decode("ascii")
    image_url = f"data:{media_type};base64,{encoded}"
    return {
        "model": config.VISION_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": prompt()},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract the vocabulary pairs from this frame."},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ],
    }


def _json_object(text: str) -> str:
    """First balanced {...} in the answer, with markdown fences stripped."""
    body = text.strip()
    if body.startswith("```"):
        newline = body.find("\n")
        body = body[newline + 1:] if newline != -1 else body[3:]
        end = body.rfind("```")
        if end != -1:
            body = body[:end]
    depth = 0
    start = -1
    for index, char in enumerate(body):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                return body[start:index + 1]
    raise VisionUnavailable("bad_json")


def parse_content(content: str) -> Answer:
    """Parse the model's message content into an Answer (bad_json / bad_shape)."""
    raw = _json_object(content)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VisionUnavailable("bad_json") from exc
    try:
        answer = Answer.model_validate(data)
    except ValidationError as exc:
        raise VisionUnavailable("bad_shape") from exc
    answer.pairs = answer.pairs[:MAX_PAIRS]
    return answer


def _status_reason(status: int) -> str:
    return _STATUS_REASONS.get(status, "http_5xx")


def _shorten(text: str) -> str:
    """Collapse whitespace and cut a provider message to one journal-safe line."""
    return " ".join(text.split())[:_DETAIL_LIMIT]


def _base_url() -> str:
    """The API base: a trailing slash or an already complete endpoint path is accepted."""
    base = config.VISION_BASE_URL.strip().rstrip("/")
    if base.endswith(_ENDPOINT):
        base = base[: -len(_ENDPOINT)].rstrip("/")
    return base


def _error_detail(response: httpx.Response) -> str:
    """The provider's own error message, truncated; never the whole body."""
    try:
        body = response.json()
    except ValueError:
        return _shorten(response.text)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return _shorten(error["message"])
        if isinstance(error, str):
            return _shorten(error)
        if isinstance(body.get("message"), str):
            return _shorten(body["message"])
    return _shorten(response.text)


def _response_content(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError as exc:
        raise VisionUnavailable("bad_json") from exc
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VisionUnavailable("bad_shape") from exc
    if not isinstance(content, str):
        raise VisionUnavailable("bad_shape")
    return content


def _to_recognition(answer: Answer, elapsed: float) -> Recognition:
    app = answer.app if answer.app in (APP_CARD, APP_DUO, APP_DROPS) else "other"
    pairs = [Pair(pair.original, pair.translation, pair.kind) for pair in answer.pairs]
    recognition = Recognition(
        usable=bool(pairs),
        app=app,
        screen_type=answer.screen_type,
        language=answer.language if answer.language in LANGUAGES else None,
        pairs=pairs,
        agreement=None,
        language_source="vision",
        elapsed=elapsed,
    )
    recognition.status, recognition.reason = recognize.vision_policy(recognition)
    return recognition


async def recognize_bytes(data: bytes, media_type: str) -> Recognition:
    """Send raw image bytes to the vision model and map the answer to a Recognition."""
    key = config.VISION_API_KEY
    if not key:
        raise VisionUnavailable("no_token")
    payload = build_payload(data, media_type)
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            base_url=_base_url(),
            timeout=config.VISION_TIMEOUT,
            headers={"Authorization": f"Bearer {key}"},
            transport=TRANSPORT,
        ) as client:
            response = await client.post(_ENDPOINT, json=payload)
    except httpx.TimeoutException as exc:
        raise VisionUnavailable("timeout") from exc
    except httpx.TransportError as exc:
        raise VisionUnavailable("transport") from exc
    elapsed = time.perf_counter() - started
    if not response.is_success:
        raise VisionUnavailable(_status_reason(response.status_code),
                                status=response.status_code,
                                detail=_error_detail(response))
    return _to_recognition(parse_content(_response_content(response)), elapsed)
