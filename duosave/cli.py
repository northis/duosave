"""Command line interface: python -m duosave <command>."""

from __future__ import annotations

import argparse
import os
import socket
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .config import DB_PATH, PATCH_PART_MB


def cmd_init(_args) -> int:
    from .db import connect, init_db

    conn = connect()
    init_db(conn)
    conn.close()
    print(f"database ready: {DB_PATH}")
    return 0


def cmd_sync(args) -> int:
    from .semantic import SemanticUnavailable
    from .sync import sync

    try:
        result = sync(
            folders=args.folders,
            limit=args.limit,
            passes=args.passes,
            retry=args.retry,
            quiet=args.quiet,
            index=args.index,
        )
    except SemanticUnavailable as exc:
        print(f"semantic index unavailable: {exc.reason}")
        return 2
    if not args.quiet:
        print(f"elapsed: {result.pop('elapsed')}s")
        for key, value in result.items():
            print(f"  {key}: {value}")
    return 0


def cmd_index(args) -> int:
    from .db import connect, init_db
    from .semantic import SemanticUnavailable, reindex

    conn = connect()
    try:
        init_db(conn)
        result = reindex(conn, full=args.full)
    except SemanticUnavailable as exc:
        print(f"semantic index unavailable: {exc.reason}")
        return 2
    finally:
        conn.close()
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


def cmd_serve(args) -> int:
    from . import config
    from .server.app import app

    if args.admin_port and args.admin_port == args.port:
        print("error: --admin-port must differ from --port (use 0 to disable the admin listener)")
        return 2
    config.ADMIN_PORT = args.admin_port
    public = (args.host, args.port)
    admin = (args.admin_host, args.admin_port) if args.admin_port else None
    if args.open:
        host, port = admin or public
        webbrowser.open(f"http://{host}:{port}")
    _run_servers(app, public, admin)
    return 0


def _bind(host: str, port: int) -> socket.socket:
    """Bind a listening socket ourselves so one uvicorn server can serve two ports."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(128)
    return sock


def _run_servers(app, public: tuple[str, int], admin: tuple[str, int] | None) -> None:
    """Serve the app on the public socket and, when enabled, on the admin socket.

    One process, one lifespan, one signal handler: the admin listener only marks
    requests as local (`scope["server"]` port), it does not duplicate state.
    """
    import uvicorn

    sockets = [_bind(*public)]
    if admin is not None:
        sockets.append(_bind(*admin))
    bound = [sock.getsockname()[:2] for sock in sockets]
    message = f"duosave: http://{bound[0][0]}:{bound[0][1]}"
    if admin is not None:
        message += f" (admin: http://{bound[1][0]}:{bound[1][1]})"
    print(message, flush=True)
    try:
        uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=sockets)
    finally:
        for sock in sockets:
            sock.close()


def cmd_snapshot(args) -> int:
    from .backup import snapshot

    print(snapshot(args.label))
    return 0


def _patch_outbox(arg: str | None) -> Path:
    from . import config

    return Path(arg) if arg else config.OUTBOX_DIR


def _print_patch_errors(exc) -> int:
    for error in exc.errors:
        print(error)
    return 1


def cmd_patch_scan(args) -> int:
    from . import patch_build, patchfmt

    try:
        result = patch_build.scan(
            patch_build.resolve_inbox(args.inbox),
            _patch_outbox(args.outbox),
            known=Path(args.known) if args.known else None,
            slice_size=args.slice_size,
        )
    except patchfmt.PatchError as exc:
        return _print_patch_errors(exc)
    print(f"new: {result.new}, known: {result.known}, processed: {result.processed}, "
          f"duplicates: {result.duplicates}, total: {result.total}")
    return 0


def cmd_patch_check(args) -> int:
    from . import patch_build, patchfmt

    try:
        result = patch_build.check(_patch_outbox(args.outbox))
    except patchfmt.PatchError as exc:
        return _print_patch_errors(exc)
    for error in result.errors:
        print(error)
    if result.exit_code == 2:
        print(f"pending: {result.pending} draft(s) without an action")
    elif result.exit_code == 0:
        print(f"ready: {result.done} record(s)")
    return result.exit_code


def cmd_patch_pack(args) -> int:
    from . import patch_build, patchfmt

    try:
        written = patch_build.pack(_patch_outbox(args.outbox), max_mb=args.max_mb,
                                   agent=args.agent)
    except patchfmt.PatchError as exc:
        return _print_patch_errors(exc)
    for path in written:
        print(path)
    return 0


def cmd_stats(_args) -> int:
    from .db import connect, stats

    conn = connect()
    data = stats(conn)
    conn.close()
    print("files:", {row["status"]: row["n"] for row in data["files"]})
    print("cards by language/app/status:")
    for row in data["cards"]:
        print(f"  {row['language']:4} {row['app'] or '-':13} {row['status']:7} {row['n']}")
    return 0


def cmd_backfill_time(_args) -> int:
    from .config import REPO
    from .db import connect, init_db
    from .filenames import created_ts as file_created_ts

    conn = connect()
    init_db(conn)
    rows = conn.execute("SELECT path FROM files WHERE created_ts IS NULL").fetchall()
    updated = 0
    for row in rows:
        full = REPO / row["path"]
        if not full.exists():
            continue
        ts = file_created_ts(full, fallback=full.stat().st_ctime)
        if ts:
            conn.execute("UPDATE files SET created_ts = ? WHERE path = ?", (ts, row["path"]))
            updated += 1
    conn.commit()
    conn.close()
    print(f"created_ts filled for {updated} of {len(rows)} files")
    return 0


def cmd_export(args) -> int:
    from .export import export

    written = export(format=args.format, out_dir=args.out_dir)
    for path in written:
        print(f"  {path}")
    return 0


def cmd_agent_queue(args) -> int:
    from .agent import write_queue

    count = write_queue(args.out, limit=args.limit)
    print(f"queue written: {args.out} ({count} items)")
    return 0


def cmd_agent_import(args) -> int:
    from .agent import import_results

    result = import_results(args.results)
    print(f"imported: {result}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="duosave", description="Duolingo/Drops cards database + site")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database").set_defaults(func=cmd_init)

    sync_parser = sub.add_parser("sync", help="scan folders, recognize, import (incremental)")
    sync_parser.add_argument("--folders", nargs="+", default=None,
                             help="image folders (default: pictures screens screens_raw)")
    sync_parser.add_argument("--limit", type=int, default=None)
    sync_parser.add_argument("--passes", type=int, default=2, help="OCR passes (1 or 2)")
    sync_parser.add_argument("--retry", action="store_true", help="re-process failed files")
    sync_parser.add_argument("--quiet", action="store_true")
    sync_parser.add_argument("--index", action="store_true", help="embed cards after sync")
    sync_parser.set_defaults(func=cmd_sync)

    index_parser = sub.add_parser("index", help="embed cards for semantic search (incremental)")
    index_parser.add_argument("--full", action="store_true", help="re-embed every card")
    index_parser.set_defaults(func=cmd_index)

    serve_parser = sub.add_parser("serve", help="run the local site")
    serve_parser.add_argument("--host", default=os.environ.get("DUOSAVE_HOST", "127.0.0.1"),
                              help="bind address (default: 127.0.0.1, env DUOSAVE_HOST)")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--admin-host",
                              default=os.environ.get("DUOSAVE_ADMIN_HOST", "127.0.0.1"),
                              help="admin bind address (default: 127.0.0.1, env DUOSAVE_ADMIN_HOST)")
    serve_parser.add_argument("--admin-port", type=int,
                              default=int(os.environ.get("DUOSAVE_ADMIN_PORT") or 8766),
                              help="admin port, 0 disables the admin listener "
                                   "(default: 8766, env DUOSAVE_ADMIN_PORT)")
    serve_parser.add_argument("--open", action="store_true")
    serve_parser.set_defaults(func=cmd_serve)

    sub.add_parser("stats", help="show database stats").set_defaults(func=cmd_stats)

    snapshot_parser = sub.add_parser("snapshot", help="consistent DB snapshot into data/backups")
    snapshot_parser.add_argument("--label", default="manual")
    snapshot_parser.set_defaults(func=cmd_snapshot)

    patch_parser = sub.add_parser("patch", help="agent-side patch tooling (no database needed)")
    patch_sub = patch_parser.add_subparsers(dest="patch_command", required=True)

    scan_parser = patch_sub.add_parser("scan", help="create drafts for new inbox images")
    scan_parser.add_argument("--inbox",
                             help="image folder (default: DUOSAVE_INBOX, then <repo>/inbox)")
    scan_parser.add_argument("--known",
                             help="known-hashes file (default: outbox/known-hashes.txt)")
    scan_parser.add_argument("--slice-size", type=int, default=20)
    scan_parser.add_argument("--outbox", help="working folder (default: <repo>/outbox)")
    scan_parser.set_defaults(func=cmd_patch_scan)

    check_parser = patch_sub.add_parser("check", help="validate drafts: 0 ok, 1 errors, 2 pending")
    check_parser.add_argument("--outbox")
    check_parser.set_defaults(func=cmd_patch_check)

    pack_parser = patch_sub.add_parser("pack", help="pack filled drafts into patch archives")
    pack_parser.add_argument("--max-mb", type=int, default=PATCH_PART_MB)
    pack_parser.add_argument("--agent", help="who recognized the images, e.g. 'opencode · model'")
    pack_parser.add_argument("--outbox")
    pack_parser.set_defaults(func=cmd_patch_pack)

    sub.add_parser("backfill-time", help="fill capture time (created_ts) from names/files for existing files"
                   ).set_defaults(func=cmd_backfill_time)

    export_parser = sub.add_parser("export", help="export cards to CSV/JSON")
    export_parser.add_argument("--format", choices=["csv", "json", "both"], default="csv")
    export_parser.add_argument("--out-dir", type=Path, default=None)
    export_parser.set_defaults(func=cmd_export)

    queue_parser = sub.add_parser("agent-queue", help="write the review queue for agent batches")
    queue_parser.add_argument("--out", type=Path, default=Path("review_queue.jsonl"))
    queue_parser.add_argument("--limit", type=int, default=None)
    queue_parser.set_defaults(func=cmd_agent_queue)

    import_parser = sub.add_parser("agent-import", help="import agent results (JSONL)")
    import_parser.add_argument("results", type=Path)
    import_parser.set_defaults(func=cmd_agent_import)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
