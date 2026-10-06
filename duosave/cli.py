"""Command line interface: python -m duosave <command>."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from .config import DB_PATH


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
    import uvicorn

    from .server.app import app

    if args.open:
        webbrowser.open(f"http://127.0.0.1:{args.port}")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
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
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--open", action="store_true")
    serve_parser.set_defaults(func=cmd_serve)

    sub.add_parser("stats", help="show database stats").set_defaults(func=cmd_stats)

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
