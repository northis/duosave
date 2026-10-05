"""Export cards to CSV (per language) and JSON."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from .config import EXPORT_DIR
from .db import card_rows_for_export, connect


def export(format: str = "csv", out_dir: Path | None = None) -> list[Path]:
    out_dir = out_dir or EXPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = connect()
    rows = card_rows_for_export(conn)
    conn.close()
    written: list[Path] = []
    if format in ("csv", "both"):
        by_lang: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_lang[row["language"]].append(row)
        for language, items in sorted(by_lang.items()):
            path = out_dir / f"{language}.csv"
            with path.open("w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerow(["original", "translation", "app", "kind", "sources"])
                for item in items:
                    writer.writerow([item["original"], item["translation"], item["app"],
                                     item["kind"], item["source_count"]])
            written.append(path)
    if format in ("json", "both"):
        path = out_dir / "cards.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(path)
    return written
