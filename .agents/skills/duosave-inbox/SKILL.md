---
name: Duosave inbox → patch
description: Use when Duolingo/Drops screenshots or share-cards in a folder (any machine, any path) must be recognized and packed into a zip patch for the Duosave site; vision-only recognition, the folder is read-only.
---

# Duosave inbox → patch

Turn a folder of phone screenshots into `outbox/duosave-patch-*.zip` archives that the
owner uploads on the site (`/admin` → «Импорт патча»). Recognition is done by **you**
(vision); there is no OCR in this flow.

## When to apply

- The user asks to «разобрать папку со скриншотами», «добавить новые картинки в Duosave»,
  or anything similar.
- The folder holds Duolingo share cards, Duolingo app screens or Drops cards.

## What you need

- A clone of this repository and `python -m pip install -r requirements-agent.txt`
  (pydantic + Pillow). Python 3.14 is recommended.
- **No** database, no Docker, no site data: the `patch scan` / `patch check` / `patch pack`
  commands never open the DB.
- Ask the user for the folder path if they did not name it.
- Ask the user to open `/admin` by its local address (see README) and download
  «Скачать список известных картинок» into `outbox/known-hashes.txt` of the clone —
  `scan` will skip images that are already in the database.

## Workflow

1. `python -m duosave patch scan --inbox "<folder>"` — drafts appear in
   `outbox/.work/slice-NNN.jsonl`; the inbox folder itself is only read.
2. Open every image from `source` and fill in the draft fields following
   `references/recognition-guide.md`; save the slice file. For parallel work use one
   sub-agent per slice file and never let two agents edit the same file.
3. `python -m duosave patch check` — repeat until it exits with code 0
   (1 = errors, 2 = drafts still without an action).
4. `python -m duosave patch pack --agent "<tool · model>"` — parts of ≤ 50 MB land in
   `outbox/`; each part is validated before it is written.
5. Report to the user: the zip paths, the number of `set` / `review` / `reject` records,
   and that each zip must be uploaded on `/admin` → «Импорт патча» → preview → «Применить».

## Rules

- Never modify, delete or rename files in the inbox folder.
- Do not edit `outbox/ledger.jsonl` unless the user explicitly asks.
- Never open or change `data/duosave.db`.
- Do not invent text that is not on the image: unsure → `review`, junk or private screens
  → `reject`.
- Field-by-field reference: `references/patch-format.md`.
