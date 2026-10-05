"""Recognition pipeline: RapidOCR + layout heuristics + confidence policy.

The logic mirrors the version validated on the golden set (see
golden_set/OCR_BASELINE.md): ink-based line splitting for share cards,
flag-based language, deterministic normalization, two-pass agreement and
a dictionary check before a pair may be auto-accepted.
"""

from __future__ import annotations

import re
import string
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .config import APP_CARD, APP_DROPS, APP_DUO, AUTO_APPS, RECOGNIZER_VERSION
from .text import (
    ENGLISH_WORDS,
    SHARED_WORDS,
    detect_language,
    detect_language_by_dict,
    dict_ok,
    foreign_evidence,
    normalize_pair,
    normalize_text,
    same_language,
)

UI_PATTERNS = {
    "continue", "got it", "check", "skip", "share", "next", "done", "close",
    "nice job!", "amazing!", "excellent!", "good!", "well done!", "awesome!",
    "correct!", "oops!", "incorrect", "explain my answer", "duolingo",
    "i know it", "learn", "hide", "show", "review", "quit", "exit",
    "combo", "in a row", "new word", "previous mistake", "keyboard",
    "share this sentence", "feed", "save image", "more", "messages",
    "words", "practice", "xp boost",
}
EXERCISE_MARKERS = {
    "type the missing word", "fill in the blank", "complete the sentence",
    "translate this sentence", "repeat what you hear", "select the correct image",
    "tap what you hear", "type what you hear", "match the pairs", "write this in",
    "read and respond", "complete the translation",
}
MARKER_MEANING = re.compile(r"^(?:.*?\b)?meaning\s*:?\s*$", re.I)
MARKER_CORRECT = re.compile(r"^(?:.*?\b)?(?:correct answer|correct solution)\s*:?\s*$", re.I)
MARKER_MEANING_INLINE = re.compile(r"^.*?meaning\s*:\s*(.+)$", re.I)
MARKER_CORRECT_INLINE = re.compile(r"^.*?(?:correct answer|correct solution)\s*:\s*(.+)$", re.I)
NUMBERISH = re.compile(r"^[\d\s:%.+×x/-]+$", re.I)

SCREEN_SHARE = "share_card"
SCREEN_DROPS = "drops_card"
SCREEN_MEANING = "meaning"
SCREEN_ANSWER = "answer_panel"
SCREEN_TILES = "tiles"
SCREEN_SELECT = "select_image"
SCREEN_UNKNOWN = "unknown"

SCREEN_TITLES = {
    "select the correct image": SCREEN_SELECT,
    "translate this sentence": SCREEN_TILES,
    "complete the translation": SCREEN_ANSWER,
}


@dataclass
class Pair:
    original: str
    translation: str
    kind: str = "sentence"


@dataclass
class Recognition:
    usable: bool = False
    app: str | None = None
    screen_type: str | None = None
    language: str | None = None
    pairs: list[Pair] = field(default_factory=list)
    agreement: bool | None = None
    language_source: str | None = None
    status: str = "skipped"
    reason: str = ""
    elapsed: float = 0.0
    version: int = RECOGNIZER_VERSION

    def to_cache(self) -> dict:
        return {
            "version": self.version,
            "usable": self.usable,
            "app": self.app,
            "screen_type": self.screen_type,
            "language": self.language,
            "language_source": self.language_source,
            "pairs": [{"original": p.original, "translation": p.translation, "kind": p.kind} for p in self.pairs],
            "agreement": self.agreement,
            "status": self.status,
            "reason": self.reason,
        }

    @classmethod
    def from_cache(cls, data: dict) -> "Recognition":
        return cls(
            usable=data.get("usable", False),
            app=data.get("app"),
            screen_type=data.get("screen_type"),
            language=data.get("language"),
            pairs=[Pair(**p) for p in data.get("pairs", [])],
            agreement=data.get("agreement"),
            language_source=data.get("language_source"),
            status=data.get("status", "skipped"),
            reason=data.get("reason", ""),
            version=data.get("version", 0),
        )


@lru_cache(maxsize=1)
def get_engine():
    from rapidocr import RapidOCR

    return RapidOCR(params={"Rec.lang_type": "pl", "Det.lang_type": "pl", "Global.log_level": "error"})


class Block:
    __slots__ = ("text", "y0", "y1", "x0", "x1", "score")

    def __init__(self, text: str, y0: float, y1: float, x0: float, x1: float, score: float):
        self.text = text
        self.y0, self.y1, self.x0, self.x1, self.score = y0, y1, x0, x1, score

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 1.0)


def is_ui(text: str) -> bool:
    lowered = text.lower().strip(" .!?»«")
    if len(lowered) > 3 and lowered in UI_PATTERNS:
        return True
    if NUMBERISH.match(text):
        return True
    if re.fullmatch(r"[ivxlcdm]{1,4}", text, re.I):
        return True
    return False


def classify_text(text: str) -> str:
    """Return en | foreign | marker_meaning | marker_correct | ui | unknown."""
    if MARKER_MEANING.match(text) or MARKER_MEANING_INLINE.match(text):
        return "marker_meaning"
    if MARKER_CORRECT.match(text) or MARKER_CORRECT_INLINE.match(text):
        return "marker_correct"
    if is_ui(text):
        return "ui"
    language = detect_language(text) or detect_language_by_dict(text)
    if language is not None:
        return "foreign"
    words = [w for w in re.split(r"[^a-z]+", text.lower()) if w]
    hits = sum(1 for w in words if w in ENGLISH_WORDS and w not in SHARED_WORDS)
    if words and hits / len(words) >= 0.34:
        return "en"
    if words and hits:
        return "unknown"
    if re.search(r"[A-Za-zĄ-ž]", text):
        return "foreign"  # lone Latin word with no English signal
    return "unknown"


def has_letters(text: str) -> bool:
    return bool(re.search(r"[A-Za-zĄ-ž]", text))


def merge_paragraphs(blocks: list[Block]) -> list[Block]:
    merged: list[Block] = []
    for block in sorted(blocks, key=lambda b: b.y0):
        if merged:
            last = merged[-1]
            vertical_overlap = min(last.y1, block.y1) - max(last.y0, block.y0)
            gap_y = block.y0 - last.y1
            overlap = min(last.x1, block.x1) - max(last.x0, block.x0)
            width = min(last.x1 - last.x0, block.x1 - block.x0, 1.0)
            gap_x = max(block.x0 - last.x1, last.x0 - block.x1)
            same_paragraph = gap_y < 0.9 * last.height and overlap > 0.45 * width
            same_line = (
                vertical_overlap > 0.6 * min(last.height, block.height)
                and gap_x < 1.5 * max(last.height, block.height)
            )
            if same_paragraph or same_line:
                last.text = f"{last.text} {block.text}".strip()
                last.y1 = max(last.y1, block.y1)
                last.x0 = min(last.x0, block.x0)
                last.x1 = max(last.x1, block.x1)
                continue
        merged.append(Block(block.text, block.y0, block.y1, block.x0, block.x1, block.score))
    return merged


def run_ocr(image: Image.Image) -> list[Block]:
    result = get_engine()(np.array(image))
    blocks: list[Block] = []
    if result is None or result.boxes is None:
        return blocks
    for text, box, score in zip(result.txts, result.boxes, result.scores):
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        blocks.append(Block(normalize_text(text), min(ys), max(ys), min(xs), max(xs), float(score)))
    return blocks


def filter_blocks(blocks: list[Block], image_height: float) -> list[Block]:
    filtered = []
    for block in blocks:
        if block.y0 < 0.045 * image_height or block.y0 > 0.94 * image_height:
            continue
        if not has_letters(block.text):
            continue
        if is_ui(block.text):
            continue
        filtered.append(block)
    return filtered


def classify_image(image: Image.Image) -> str:
    """drops | app | junk — quick background/colour heuristic."""
    small = image.convert("RGB").resize((32, 64))
    pixels = list(small.getdata())
    n = len(pixels)
    mean = tuple(sum(p[i] for p in pixels) // n for i in range(3))
    from collections import Counter

    quant = Counter((p[0] // 24 * 24, p[1] // 24 * 24, p[2] // 24 * 24) for p in pixels)
    _, dom_count = quant.most_common(1)[0]
    share = dom_count / n
    mx, mn = max(mean), min(mean)
    saturation = (mx - mn) / mx if mx else 0.0
    value = mx / 255
    if saturation > 0.35 and share > 0.45:
        return "drops"
    if value < 0.3:
        return "app"
    return "junk"


def flag_language(image: Image.Image) -> str | None:
    """Course language from the flag on a Duolingo share card."""
    width, height = image.size
    crop = image.convert("RGB").crop(
        (int(width * 0.05), int(height * 0.12), int(width * 0.30), int(height * 0.30))
    )
    pixels = list(crop.getdata())
    n = len(pixels)
    red = sum(1 for r, g, b in pixels if r > 170 and g < 110 and b < 110)
    yellow = sum(1 for r, g, b in pixels if r > 200 and g > 150 and b < 80)
    green = sum(1 for r, g, b in pixels if g > 130 and g > r + 50 and g > b + 50)
    white = sum(1 for r, g, b in pixels if r > 225 and g > 225 and b > 225)
    if green > n * 0.01 and yellow > n * 0.01:
        return "pt"
    if red > n * 0.01 and yellow > n * 0.01:
        return "es"
    if red > n * 0.01 and white > n * 0.01 and green < n * 0.005 and yellow < n * 0.005:
        return "pl"
    return None


def line_dark_ratio(gray: Image.Image, block: Block) -> float:
    box = (
        max(int(block.x0) - 2, 0),
        max(int(block.y0) - 2, 0),
        min(int(block.x1) + 2, gray.width),
        min(int(block.y1) + 2, gray.height),
    )
    pixels = list(gray.crop(box).getdata())
    if not pixels:
        return 0.0
    return sum(1 for value in pixels if value < 100) / len(pixels)


def pair_share_card(blocks: list[Block], gray: Image.Image) -> tuple[str, str, str] | None:
    lines = sorted(blocks, key=lambda b: b.y0)
    if len(lines) < 2:
        return None
    ratios = [line_dark_ratio(gray, block) for block in lines]
    labels = ["foreign" if ratio >= 0.128 else "en" for ratio in ratios]
    if "foreign" in labels and "en" in labels:
        first_en = labels.index("en")
        if all(label == "foreign" for label in labels[:first_en]) and all(
            label == "en" for label in labels[first_en:]
        ):
            original = normalize_text(" ".join(b.text for b in lines[:first_en]))
            translation = normalize_text(" ".join(b.text for b in lines[first_en:]))
            if original and translation and original.lower() != translation.lower():
                return SCREEN_SHARE, original, translation
    return None


def pair_drops(blocks: list[Block], image_height: float) -> tuple[str, str, str] | None:
    paragraphs = [
        p
        for p in merge_paragraphs(blocks)
        if p.y0 < 0.94 * image_height
        and classify_text(p.text) in ("en", "foreign")
        and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", p.text)) >= 3
    ]
    if len(paragraphs) < 2:
        return None
    paragraphs.sort(key=lambda p: p.y0)
    if len(paragraphs) > 2:
        gaps = [(paragraphs[i + 1].y0 - paragraphs[i].y1, i) for i in range(len(paragraphs) - 1)]
        gap, index = min(gaps)
        if gap > 3 * max(paragraphs[index].height, paragraphs[index + 1].height):
            return None
        paragraphs = [paragraphs[index], paragraphs[index + 1]]
    labels = [classify_text(p.text) for p in paragraphs]
    if labels.count("en") == 1 and labels.count("foreign") == 1:
        en_para = paragraphs[labels.index("en")]
        foreign_para = paragraphs[labels.index("foreign")]
        if same_language(foreign_para.text, en_para.text):
            return None
        if foreign_evidence(en_para.text) is not None:
            return None
        return SCREEN_DROPS, foreign_para.text, en_para.text
    first, second = sorted(paragraphs, key=lambda p: p.y0)
    if first.height <= second.height:
        original, translation = second.text, first.text
    else:
        original, translation = first.text, second.text
    if same_language(original, translation) or foreign_evidence(translation) is not None:
        return None
    return SCREEN_DROPS, original, translation


def pair_marker(blocks: list[Block]) -> tuple[str, str, str] | None:
    paragraphs = merge_paragraphs(blocks)
    types = [(classify_text(p.text), p) for p in paragraphs]
    screen_type = SCREEN_UNKNOWN
    for kind, para in types:
        if kind == "ui":
            continue
        lowered = para.text.lower()
        for title, mapped in SCREEN_TITLES.items():
            if title in lowered:
                screen_type = mapped
    for marker, want in (("marker_meaning", "foreign"), ("marker_correct", "en")):
        for index, (kind, para) in enumerate(types):
            if kind != marker:
                continue
            after: list[str] = []
            for next_kind, next_para in types[index + 1 :]:
                if next_kind in ("ui", "marker_meaning", "marker_correct"):
                    break
                after.append(next_para.text)
            payload = ""
            if marker == "marker_meaning":
                match = MARKER_MEANING_INLINE.match(para.text)
                screen_type = SCREEN_MEANING
            else:
                match = MARKER_CORRECT_INLINE.match(para.text)
                screen_type = SCREEN_ANSWER
            payload = normalize_text(match.group(1)) if match else ""
            payload = normalize_text(" ".join([payload, *after]).strip())
            candidates = [p for k, p in types[:index] if k == want]
            if payload and candidates:
                clusters: list[list[Block]] = []
                for candidate in sorted(candidates, key=lambda p: p.y0):
                    if clusters:
                        last = clusters[-1][-1]
                        if candidate.y0 - last.y1 < 1.2 * max(candidate.height, last.height):
                            clusters[-1].append(candidate)
                            continue
                    clusters.append([candidate])
                best_text, best_rank = "", (-1, -1)
                for cluster in clusters:
                    text = normalize_text(" ".join(p.text for p in cluster))
                    rank = (1 if len(text.split()) >= 2 else 0, len(text))
                    if rank > best_rank and text:
                        best_rank, best_text = rank, text
                if best_text and best_text.lower() != payload.lower():
                    if marker == "marker_correct":
                        return screen_type, payload, best_text
                    return screen_type, best_text, payload
    return None


def preprocess_variant(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    mean = sum(gray.resize((8, 8)).getdata()) / 64
    prepared = ImageOps.invert(image) if mean < 110 else image
    prepared = ImageOps.autocontrast(prepared)
    return prepared.resize((int(prepared.width * 1.5), int(prepared.height * 1.5)), Image.LANCZOS)


def _extract_once(image: Image.Image, mode: str) -> tuple[str | None, str, str, str | None, str | None, bool]:
    """Return (screen_type, original, translation, language, language_source, marker)."""
    blocks = run_ocr(image)
    if not blocks:
        return None, "", "", None, None, False
    height = float(image.size[1])
    marker = any(any(title in block.text.lower() for title in EXERCISE_MARKERS) for block in blocks)
    filtered = filter_blocks(blocks, height)
    flag = None
    if mode == "card":
        result = pair_share_card(filtered, image.convert("L"))
        flag = flag_language(image)
    elif mode == "drops":
        result = pair_drops(filtered, height)
    else:
        result = pair_marker(filtered)
    if result is None:
        return None, "", "", None, None, marker
    screen_type, original, translation = result
    if flag is not None:
        language, source = flag, "flag"
    else:
        by_text = detect_language(original)
        if by_text is not None:
            language, source = by_text, "text"
        else:
            language = detect_language_by_dict(original)
            source = "dict" if language else None
    original, translation = normalize_pair(original, translation, language)
    if language is None:
        language = detect_language(original) or detect_language_by_dict(original)
        source = "post" if language else None
    return screen_type, original, translation, language, source, marker


def _policy(recognition: Recognition, passes: int) -> tuple[str, str]:
    if not recognition.usable:
        return "skipped", recognition.reason or "no_pair"
    if recognition.app not in AUTO_APPS:
        return "review", "app_screen"
    if passes >= 2:
        if recognition.agreement is not True:
            return "review", "pass_disagreement"
    elif recognition.app == APP_CARD:
        if recognition.language_source != "flag":
            return "review", "language_uncertain"
    else:
        return "review", "single_pass"
    if recognition.language not in ("pl", "es", "pt"):
        return "review", "language_unknown"
    first = recognition.pairs[0]
    if not dict_ok(first.original, recognition.language):
        return "review", "dictionary"
    return "auto", ""


def recognize_image(path: Path, kind_hint: str = "auto", passes: int = 2) -> tuple[Recognition, dict]:
    """Run the full recognition pipeline for one image."""
    started = time.perf_counter()
    with Image.open(path) as raw:
        image = raw.convert("RGB")
        if kind_hint == "auto":
            kind = classify_image(image)
        else:
            kind = kind_hint
    app = {"card": APP_CARD, "drops": APP_DROPS, "app": APP_DUO}.get(kind, "other")
    recognition = Recognition(app=app)
    if kind == "junk":
        recognition.reason = "not_app"
        recognition.elapsed = time.perf_counter() - started
        return recognition, recognition.to_cache()

    mode = {"drops": "drops", "app": "app"}.get(kind, "card")
    screen_type, original, translation, language, source, marker = _extract_once(image, mode)
    if not original or not translation:
        # OCR found no pair: route to the review queue (agent/vision) instead of
        # silently dropping — chip-bank answers and odd layouts live here.
        if app == APP_DUO:
            recognition.reason = "app_no_pair" if marker else "app_junk"
        else:
            recognition.reason = "no_pair"
        recognition.status = "review"
        recognition.elapsed = time.perf_counter() - started
        return recognition, recognition.to_cache()

    recognition.usable = True
    recognition.screen_type = screen_type
    recognition.language = language
    recognition.language_source = source
    recognition.pairs = [Pair(original, translation)]

    if passes >= 2:
        second = _extract_once(preprocess_variant(image), mode)
        second_pair = (second[1], second[2]) if second[1] else None
        recognition.agreement = ((original, translation) == second_pair) if second_pair else False

    status, reason = _policy(recognition, passes)
    recognition.status = status
    recognition.reason = reason
    recognition.elapsed = time.perf_counter() - started
    return recognition, recognition.to_cache()
