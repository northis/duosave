# AGENTS.md — Duosave

Duosave is a personal Duolingo/Drops card database: a pipeline that recognizes screenshots
(OCR, Drops crops, embeddings for semantic search) and a local FastAPI site with search, a
review queue and a maintenance page (`/admin`) for patches and backups.

## Layout

| Path | What is there |
| --- | --- |
| `duosave/` | pipeline and CLI (`sync`, `index`, `serve`, `snapshot`, `patch …`) |
| `duosave/server/` | FastAPI app, admin router, security guards, static UI |
| `tests/` | pytest suite (offline: no Docker, no network, no real models) |
| `tools/` | scripts run by hand whose output is committed (`make_icons.py` → `duosave/server/static/icons/`) |
| `deploy/` | host-side update script (`windows/update.ps1`: git pull + docker build + restart) |
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
powershell -ExecutionPolicy Bypass -File deploy\windows\update.ps1  # console update on the host
```

## Versioning

- Every change bumps the **minor** version: edit `__version__` in `duosave/__init__.py`
  (2.3.0 → 2.4.0) and the assertion in `tests/test_buildinfo.py` in the same commit.
- Tag that commit with the same version: `git tag -a v2.4.0 -m "duosave 2.4.0"`.
- Publish the tag together with the branch: `git push --follow-tags origin master` (or
  `git push origin master v2.4.0`). Run `git config push.followTags true` once per clone so a
  plain `git push` carries tags too — a tag that was never pushed does not reach the server.
- The host update script builds from the tagged commit and bakes `vX.Y.Z` into the image (the
  site header shows it); it warns when the deployed commit has no matching tag.

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
