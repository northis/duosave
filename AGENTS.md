# AGENTS.md — Duosave

Duosave is a personal Duolingo/Drops card database: a pipeline that recognizes screenshots
(OCR, Drops crops, embeddings for semantic search) and a local FastAPI site with search, a
review queue and a maintenance page (`/admin`) for updates, patches and backups.

## Layout

| Path | What is there |
| --- | --- |
| `duosave/` | pipeline and CLI (`sync`, `index`, `serve`, `snapshot`, `patch …`) |
| `duosave/server/` | FastAPI app, admin router, security guards, static UI |
| `tests/` | pytest suite (offline: no Docker, no network, no real models) |
| `deploy/` | host-side deployment helpers (Windows scheduled task for the updater) |
| `.agents/skills/` | agent skills (table below) |
| `.sdd/specs/` | specifications and implementation plans (local, git-ignored) |

## Commands

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt   # full install
python -m pytest -q                                                 # the whole suite
python -m duosave serve                                             # site + admin on 8765/8766
python -m duosave sync --index                                      # recognize new images
python -m duosave snapshot --label manual                           # consistent DB snapshot
python -m duosave patch scan --inbox "<folder>"                     # agent-side patches
docker compose up -d --build                                        # production on the host
python -m duosave.updater status                                    # updater on the host
```

## Conventions

- Python 3.14, `from __future__ import annotations`, type hints, short functions.
- FastAPI + vanilla JS without a build step; all UI strings RU/EN (`I18N` in `app.js`).
- Heavy imports (OCR, ML, FastAPI) stay lazy inside CLI commands.
- Paths and limits are read at call time through `duosave.config` (`from . import config`),
  so tests can point them at a temporary repository.
- Tests are offline: `TestClient(app)`, fixtures `tmp_db` / `tmp_repo` / `client` /
  `admin_client` / `fake_embedder`; no Docker, no network, no real model downloads.
- README is Russian; code, comments and docstrings are English.

## Data safety

- The working copy **is** production: never run `git reset`, `git clean`, `git stash` or
  `git checkout` here unless the user explicitly asks.
- Never open `data/duosave.db` from the host while the container is running (WAL over a
  bind mount): use `docker compose exec duosave …`.
- The maintenance page lives on the local listener only (`DUOSAVE_ADMIN_PORT`, default
  8766) — never publish that port to the internet.
- Never commit `data/`, `pictures/`, `screens/`, `inbox/`, `outbox/`, `.env`.

## Skills

| Skill | Use it when |
| --- | --- |
| [`.agents/skills/duosave-inbox/SKILL.md`](.agents/skills/duosave-inbox/SKILL.md) | Duolingo/Drops screenshots in a folder must be recognized and packed into a zip patch for the site; the folder is read-only |
