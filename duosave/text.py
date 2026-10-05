"""Text helpers: normalization, diacritic folding, language detection, fixes.

Word lists are lazy-loaded so that serving the site does not pay the cost.
"""

from __future__ import annotations

import re
import string
import unicodedata
from functools import lru_cache
from pathlib import Path

from .config import LANGUAGES, WORDLIST_DIR

CYRILLIC = re.compile(r"[\u0400-\u04FF]")

PL_STRONG = set("ąćęłńóśźż")
PT_STRONG = set("ãõçêôà")
ES_STRONG = set("ñ¿¡ü")
WEAK_ACCENTS = set("áéíóúâ")

FOLD_MAP = str.maketrans({
    "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D",
    "æ": "ae", "œ": "oe", "ß": "ss",
})

NUMBERISH = re.compile(r"^[\d\s:%.+×x/-]+$", re.I)

ENGLISH_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of", "in",
    "on", "at", "for", "with", "and", "but", "or", "not", "no", "yes", "i", "you",
    "he", "she", "it", "we", "they", "my", "your", "his", "her", "our", "their",
    "this", "that", "these", "those", "there", "here", "do", "does", "did", "don't",
    "doesn't", "didn't", "can", "can't", "will", "won't", "would", "should", "have",
    "has", "had", "what", "when", "where", "who", "why", "how", "which", "am",
    "going", "get", "got", "like", "just", "very", "much", "many", "some", "any",
    "one", "two", "three", "day", "today", "tomorrow", "yesterday", "good", "bad",
    "big", "small", "new", "old", "eat", "drink", "go", "come", "see", "know",
    "want", "need", "love", "work", "home", "house", "car", "book", "water",
    "food", "friend", "friends", "family", "mom", "dad", "boy", "girl", "man",
    "woman", "people", "time", "year", "week", "morning", "night", "please",
    "fruit", "passion", "bath", "toy", "snorkel", "watch", "battery", "phone",
    "clock", "line", "poo", "fever", "flavor", "herb", "soon", "vote", "young",
    "genius", "sugar", "mountain", "climbed", "already", "half", "kilogram",
    "attentive", "salesperson", "wave", "huge", "look", "miss", "truth", "tell",
}
PL_WORDS = {
    "nie", "się", "sie", "jest", "jestem", "jesteś", "jesteśmy", "że", "ze",
    "mnie", "mi", "mną", "ciebie", "jego", "jej", "ich", "mój", "moja", "moje",
    "ty", "on", "ona", "ono", "my", "wy", "oni", "one", "tak", "jak", "gdzie",
    "kiedy", "dlaczego", "który", "która", "które", "będę", "będzie", "chcę",
    "mam", "masz", "mamy", "macie", "mają", "lubię", "wczoraj", "dzisiaj",
    "jutro", "bardzo", "dobrze", "przyszli", "przyszedł", "przyjaciele",
}
PT_WORDS = {
    "não", "nao", "são", "sao", "você", "voce", "estou", "está", "um", "uma",
    "uns", "umas", "com", "do", "da", "dos", "das", "os", "as", "eu", "nós",
    "nos", "eles", "elas", "meu", "minha", "seu", "sua", "dele", "dela",
    "gosto", "quero", "tenho", "vou", "vai", "mais", "muito", "muita", "sim",
    "obrigado", "obrigada", "aqui", "ali", "qual",
}
ES_WORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "es", "estoy",
    "eres", "somos", "soy", "usted", "tú", "tu", "ellos", "ellas", "nosotros",
    "del", "más", "mas", "sí", "si", "cómo", "como", "dónde", "donde", "cuándo",
    "cuando", "porqué", "gusta", "quiero", "tengo", "tiene", "voy", "va",
    "muy", "mucho", "mucha", "bien", "gracias", "aquí", "allí", "cuál", "pronto",
    "yo", "ella", "él", "les",
}
SHARED_WORDS = {
    "que", "para", "con", "por", "me", "mi", "lo", "se", "y", "e", "o", "a",
    "de", "no", "está", "esta", "tu", "su", "en", "não", "un", "una",
}
AMBIGUOUS_FOREIGN = {
    "my", "on", "to", "do", "no", "i", "a", "we", "me", "he", "as", "so",
    "it", "is", "us", "an", "am", "go", "by", "or", "at", "if", "in", "of", "be",
}

PL_BIGRAMS = ("cz", "sz", "rz", "dz", "ść", "prz", "trz", "stw", "ł")
PT_BIGRAMS = ("ão", "õe", "ç", "nh", "lh", "ção", "ões", "eir", "inh")
ES_BIGRAMS = ("ñ", "ll", "ción", "ied")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    for src, dst in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"')):
        text = text.replace(src, dst)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=4096)
def fold_text(text: str) -> str:
    """Diacritic-insensitive form used for search and comparisons."""
    folded = normalize_text(text).translate(FOLD_MAP)
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


# ------------------------------------------------------------------ word lists


@lru_cache(maxsize=1)
def _load_50k() -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for code in LANGUAGES:
        path = WORDLIST_DIR / f"{code}_50k.txt"
        words: set[str] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.split()
                if parts:
                    words.add(parts[0].casefold())
        result[code] = words
    return result


@lru_cache(maxsize=1)
def _load_full() -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for code in LANGUAGES:
        path = WORDLIST_DIR / f"{code}_full.txt"
        words: set[str] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.split()
                if parts:
                    words.add(parts[0].casefold())
        result[code] = words or _load_50k().get(code, set())
    return result


@lru_cache(maxsize=1)
def _load_pl_aux() -> tuple[set[str], dict[str, int]]:
    path = WORDLIST_DIR / "pl_full.txt"
    l_words: set[str] = set()
    counts: dict[str, int] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split()
            if not parts:
                continue
            word = parts[0].casefold()
            if "ł" in word:
                l_words.add(word)
            if len(parts) >= 2 and ("t" in word or "ł" in word):
                try:
                    counts[word] = int(parts[1])
                except ValueError:
                    continue
    return l_words, counts


def full_lists() -> dict[str, set[str]]:
    return _load_full()


def full_list(code: str) -> set[str]:
    return _load_full().get(code, set())


# ------------------------------------------------------------- language tools


def bigram_score(text: str, bigrams: tuple[str, ...]) -> int:
    lower = text.lower()
    return sum(lower.count(bigram) for bigram in bigrams)


def detect_language(text: str) -> str | None:
    """Heuristic pl/es/pt detection; None when the signal is too weak."""
    if not text or CYRILLIC.search(text):
        return None
    lower = text.lower()
    scores = {"pl": 0.0, "pt": 0.0, "es": 0.0}
    for ch in lower:
        if ch in PL_STRONG:
            scores["pl"] += 2.0
        elif ch in PT_STRONG:
            scores["pt"] += 2.0
        elif ch in ES_STRONG:
            scores["es"] += 2.0
        elif ch in WEAK_ACCENTS:
            scores["pt"] += 0.5
            scores["es"] += 0.5
    for word in re.findall(r"[a-zà-ÿąćęłńóśźż]+", lower):
        if word in SHARED_WORDS:
            continue
        if word in PL_WORDS:
            scores["pl"] += 1.5
        if word in PT_WORDS:
            scores["pt"] += 1.5
        if word in ES_WORDS:
            scores["es"] += 1.5
    if re.match(r"^(o|os|as)\s+\w", lower):
        scores["pt"] += 1.5
    scores["pl"] += 0.6 * bigram_score(text, PL_BIGRAMS)
    scores["pt"] += 0.6 * bigram_score(text, PT_BIGRAMS)
    scores["es"] += 0.6 * bigram_score(text, ES_BIGRAMS)

    best = max(scores, key=scores.get)
    ordered = sorted(scores.values(), reverse=True)
    if ordered[0] < 0.5:
        return None
    if len(lower.split()) > 4 and ordered[0] - ordered[1] < 1.0 and ordered[0] < 3.5:
        return None
    return best


def detect_language_by_dict(text: str) -> str | None:
    words = re.findall(r"[a-zà-ÿąćęłńóśźż]+", text.casefold())
    counts = {code: 0 for code in LANGUAGES}
    lists = full_lists()
    for word in words:
        if len(word) < 3 or word in SHARED_WORDS:
            continue
        for code in LANGUAGES:
            if word in lists.get(code, set()):
                counts[code] += 1
    best = max(counts, key=counts.get)
    ordered = sorted(counts.values(), reverse=True)
    if ordered[0] >= 1 and ordered[0] > ordered[1]:
        return best
    return None


def foreign_evidence(text: str) -> str | None:
    """Language only with strong evidence: specific chars or distinctive words."""
    language = detect_language(text)
    if language is None:
        return None
    strong = {"pl": PL_STRONG, "pt": PT_STRONG, "es": ES_STRONG}[language]
    if any(ch in strong for ch in text):
        return language
    distinctive = {"pl": PL_WORDS, "pt": PT_WORDS, "es": ES_WORDS}[language]
    for word in re.findall(r"[a-zà-ÿąćęłńóśźż]+", text.casefold()):
        if word in distinctive and word not in AMBIGUOUS_FOREIGN:
            return language
    return None


def same_language(first: str, second: str) -> bool:
    first_lang = foreign_evidence(first) or detect_language_by_dict(first)
    second_lang = foreign_evidence(second) or detect_language_by_dict(second)
    return first_lang is not None and first_lang == second_lang


def dict_ok(text: str, language: str | None) -> bool:
    """All lowercase content words are known to the language dictionary."""
    if language not in LANGUAGES:
        return False
    known = full_list(language)
    if not known:
        return False
    for raw in re.split(r"[\s,.;:!?¡¿()»«\"]+", text):
        if not raw or raw[:1].isupper() or any(ch.isdigit() for ch in raw):
            continue
        for token in raw.split("-"):
            token = token.strip("'").casefold()
            if len(token) >= 3 and token not in known:
                return False
    return True


# ------------------------------------------------------------------- fixes


def fix_zero_article(text: str, language: str | None) -> str:
    text = re.sub(r"^0\b", "O", text)
    if language == "pt":
        text = re.sub(r"\b0\b", "o", text)
    return text


def restore_spanish_marks(text: str, language: str | None) -> str:
    if language != "es" or not text:
        return text
    for closing, opening in (("!", "¡"), ("?", "¿")):
        if closing in text and opening not in text:
            match = re.match(r"^([A-Za-zÁÉÍÓÚÑÜ][^,!?¿¡]{0,20},)\s*", text)
            if match:
                text = f"{text[:match.end(1)]} {opening}{text[match.end(1):].lstrip()}"
            else:
                text = opening + text
    return text


def fix_polish_l(text: str) -> str:
    l_words, counts = _load_pl_aux()
    if not l_words:
        return text
    valid = full_list("pl")
    fixed_tokens = []
    for token in text.split():
        stripped = token.strip(string.punctuation)
        core = stripped.casefold()
        if core and "t" in core:
            candidates = set()
            for index, ch in enumerate(core):
                if ch == "t":
                    candidate = f"{core[:index]}ł{core[index + 1:]}"
                    if candidate in l_words:
                        candidates.add(candidate)
            if len(candidates) == 1:
                replacement = candidates.pop()
                original_count = counts.get(core, 0)
                candidate_count = counts.get(replacement, 0)
                unknown = core not in valid
                much_more_frequent = candidate_count >= 100 and candidate_count > 10 * max(original_count, 1)
                if unknown or much_more_frequent:
                    if stripped[:1].isupper():
                        replacement = replacement[:1].upper() + replacement[1:]
                    token = token.replace(stripped, replacement)
        fixed_tokens.append(token)
    return " ".join(fixed_tokens)


def fix_glued_article(text: str, language: str | None) -> str:
    if not text or language not in (None, "pt"):
        return text
    words_pt = full_list("pt")
    if not words_pt:
        return text
    match = re.match(r"^(o|a|os|as)([a-zà-ÿ]{4,})(\s.*)?$", text)
    if not match:
        return text
    article, rest, tail = match.group(1), match.group(2), match.group(3) or ""
    whole = f"{article}{rest}"
    if (
        rest in words_pt
        and whole not in words_pt
        and whole not in full_list("pl")
        and whole not in full_list("es")
    ):
        return f"{article} {rest}{tail}"
    return text


def normalize_pair(original: str, translation: str, language: str | None) -> tuple[str, str]:
    original = normalize_text(original)
    original = fix_zero_article(original, language)
    original = restore_spanish_marks(original, language)
    if language == "pl":
        original = fix_polish_l(original)
    original = fix_glued_article(original, language)
    return original, normalize_text(translation)
