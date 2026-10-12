# Patch format v1 — agent reference

Source of truth: `duosave/patchfmt.py` and `contracts/patch-format.md`. This page is the
short version: what `scan` fills in, what you fill in, what `pack` produces.

## Draft — `outbox/.work/slice-NNN.jsonl`

One JSON object per line. `scan` fills in `source`, `sha256`, `size`, `created_ts`,
`safe_name`, `duplicate_of` — never change those. You fill in:

| Field | Values |
| --- | --- |
| `action` | `set` — pairs are certain; `review` — a human must check; `reject` — not a language-app screen or private content |
| `folder` | `pictures` (Duolingo share cards) or `screens` (app screens, Drops) |
| `app` | `duolingo_card` (only with `pictures/`), `duolingo_app` or `drops` (only with `screens/`) |
| `screen_type` | `share_card`, `drops_card`, `meaning`, `answer_panel`, `tiles`, `select_image`, `unknown` |
| `language` | `pl`, `es`, `pt`; `unk` only with `action: review` |
| `pairs` | `set`: 1–10 pairs; `review`: 0–10 pairs; `reject`: keep `[]` |
| `note` | short reason for `review`/`reject`, ≤ 500 characters |

A draft with `action: null` is unfinished: `check` exits with code 2.

<!-- example: draft -->
```json
{"source": "D:/Phone/Screenshots/IMG_20261010_101010.png", "sha256": "0939581f0dfea9e2cb72da7e5d596bdc7de4ab273705d4957acd4c7ff95ad350", "size": 412345, "created_ts": 1760090410, "safe_name": "IMG_20261010_101010.png", "duplicate_of": null, "action": null, "folder": null, "app": null, "screen_type": null, "language": null, "pairs": [], "note": ""}
{"source": "D:/Phone/Screenshots/IMG_20261010_101011.png", "sha256": "10e88f976f48017a08e1c7dfffe80b80ac618092a1c4c8068dd403cb80a6993c", "size": 398001, "created_ts": 1760090411, "safe_name": "IMG_20261010_101011.png", "duplicate_of": null, "action": "set", "folder": "screens", "app": "drops", "screen_type": "drops_card", "language": "pt", "pairs": [{"original": "o abacaxi", "translation": "pineapple", "kind": "word"}], "note": ""}
```

`duplicate_of` is set by `scan` for a copy of an image already seen in the same folder:
such records need no action, are never packed and are logged as `duplicate`.

## Record — what `pack` writes into `records.jsonl`

One line per image; `file` is `<folder>/<safe_name>`, `sha256` must match the image.

<!-- example: record -->
```json
{"file": "screens/IMG_20261010_101011.png", "sha256": "10e88f976f48017a08e1c7dfffe80b80ac618092a1c4c8068dd403cb80a6993c", "created_ts": 1760090411, "action": "set", "app": "drops", "screen_type": "drops_card", "language": "pt", "pairs": [{"original": "o abacaxi", "translation": "pineapple", "kind": "word"}], "note": ""}
{"file": "pictures/1760091234.png", "sha256": "3293f0d2e62a5eb4ea52785d87cad341f9d365d1f8999c2c1e7baf59662c4e49", "created_ts": null, "action": "review", "app": "duolingo_card", "screen_type": "share_card", "language": "es", "pairs": [], "note": "text partially covered"}
```

## Ledger — `outbox/ledger.jsonl`

`pack` appends one line per processed image (packed / rejected / duplicate). `scan`
skips every sha256 listed here, so an image is never recognized twice on this machine.

<!-- example: ledger -->
```json
{"sha256": "0939581f0dfea9e2cb72da7e5d596bdc7de4ab273705d4957acd4c7ff95ad350", "source": "D:/Phone/Screenshots/IMG_20261010_101010.png", "outcome": "packed", "patch_id": "20261012T103105Z-3f9c2a1b-p1", "note": "", "at": "2026-10-12T10:31:05Z"}
{"sha256": "10e88f976f48017a08e1c7dfffe80b80ac618092a1c4c8068dd403cb80a6993c", "source": "D:/Phone/Screenshots/bank.png", "outcome": "rejected", "patch_id": null, "note": "banking app", "at": "2026-10-12T10:31:05Z"}
```

To process an image again, remove its line from the ledger (only when the user asks).

## Known list — `outbox/known-hashes.txt`

Downloaded from the site (`/admin` → «Скачать список известных картинок»). `scan` skips
these sha256 values: they are already in the site's database.

<!-- example: known -->
```text
# duosave known-hashes v1 2026-10-12T10:20:00Z 2
0939581f0dfea9e2cb72da7e5d596bdc7de4ab273705d4957acd4c7ff95ad350
10e88f976f48017a08e1c7dfffe80b80ac618092a1c4c8068dd403cb80a6993c
```

## Exit codes of `check`

| Code | Meaning |
| --- | --- |
| 0 | every record is filled in and every source is unchanged |
| 1 | errors (schema, missing or changed source) — printed as `slice-NNN.jsonl:<line>: …` |
| 2 | there are drafts without an action |

## What `pack` does

- Refuses to run unless `check` exits with 0.
- Splits `set`/`review` records into parts of ≤ 50 MB (sum of image sizes) and writes
  `outbox/duosave-patch-<patch_id>.zip`; every part is validated against the server rules.
- `reject` records and duplicates never enter an archive.
- Only after all parts are written: the ledger is appended and the slices move to
  `outbox/.work/done/<group>/`.

## Limits (server side)

| Limit | Value |
| --- | --- |
| archive members | ≤ 2000 |
| unpacked size | ≤ 512 MiB |
| one image | ≤ 40 megapixels |
| pairs per record | ≤ 10 |
| `original` / `translation` / `note` | ≤ 500 characters |
| upload per part | ≤ `DUOSAVE_PATCH_MAX_MB` (100 MB by default) |
