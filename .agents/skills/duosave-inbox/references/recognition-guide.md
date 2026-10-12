# Recognition guide — what to see and what to write

You are the recognizer: there is no OCR in this flow. Open each image from `source` and
fill the draft fields. When unsure — use `review`, never guess.

## 1. Which folder and app?

| What you see | `folder` | `app` | `screen_type` |
| --- | --- | --- | --- |
| Duolingo «Поделиться» card: square, bright, flag, a phrase and its translation | `pictures` | `duolingo_card` | `share_card` |
| Duolingo app exercise screen (dark UI, tiles/answers) | `screens` | `duolingo_app` | `meaning`, `answer_panel`, `tiles`, `select_image` or `unknown` |
| Drops: flat single-colour card, one word + a picture | `screens` | `drops` | `drops_card` |

## 2. Original and translation

- Duolingo share card: the big phrase in the learning language is `original`, the English
  line under it is `translation`. The flag tells you the language.
- Duolingo app screen: `original` is the target-language sentence on the screen (the
  prompt or the correct answer), `translation` is the English line if the screen shows it.
  If only one language is visible, `translation` is the English text of the exercise;
  if there is no English text at all → `review`.
- Drops: the word on the card is `original`, the English word is `translation`.

## 3. Language

Pick from the flag and the diacritics:

| `language` | Typical letters |
| --- | --- |
| `pl` | ą ć ę ł ń ó ś ź ż |
| `es` | ñ ¿ ¡ á é í ó ú |
| `pt` | ã õ ç â ê ô à |

`unk` is allowed only with `action: review` (for example, a screen where the language is
not visible).

## 4. `kind`

- `word` — a single word, including an article (`o abacaxi`, `la casa`);
- `phrase` — a short expression that is not a full sentence;
- `sentence` — a full sentence (the default).

## 5. Text rules

- Copy the diacritics and the letter case exactly as on the screen.
- Do not add or remove punctuation; do not drop articles; collapse repeated spaces.
- `translation` is the English text from the screen, not your own translation.
- Several pairs on one screen (for example, a list of words) → several `pairs` entries.
- Keep `created_ts` as `scan` filled it; `pack` keeps the original capture time.

## 6. When to use `review`

- You are not sure about a letter or a word.
- Part of the text is covered by the keyboard, a banner or a tooltip.
- The answer is assembled from tiles and cannot be read reliably.
- The language is unclear → `language: "unk"`, `pairs: []`, explain in `note`.

## 7. When to use `reject`

Not a language-learning screen: ratings and streak dialogs, the shop, settings,
chats, banking or other private screens. Put a short reason into `note` — without
retelling private content. Rejected images are never packed; only the ledger records them.

## 8. Examples

Filled draft for a Drops card:

```json
{"action": "set", "folder": "screens", "app": "drops", "screen_type": "drops_card", "language": "pt", "pairs": [{"original": "o abacaxi", "translation": "pineapple", "kind": "word"}], "note": ""}
```

Filled draft for a Duolingo share card:

```json
{"action": "set", "folder": "pictures", "app": "duolingo_card", "screen_type": "share_card", "language": "es", "pairs": [{"original": "¿Dónde está la estación?", "translation": "Where is the station?", "kind": "sentence"}], "note": ""}
```

Unsure about the exercise screen:

```json
{"action": "review", "folder": "screens", "app": "duolingo_app", "screen_type": "tiles", "language": "pl", "pairs": [{"original": "Zły chłopiec pije kawę.", "translation": "The bad boy is drinking coffee.", "kind": "sentence"}], "note": "unsure about the ending of «chłopiec»"}
```

Junk screen:

```json
{"action": "reject", "folder": null, "app": null, "screen_type": null, "language": null, "pairs": [], "note": "banking app screen"}
```
