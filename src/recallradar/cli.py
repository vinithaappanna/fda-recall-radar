"""Read-only query CLI over the committed recall archive (data/recalls_history.csv).

  python scripts/query.py recall D-0082-2027
  python scripts/query.py firm "par health"      # substring match, case-insensitive
  python scripts/query.py theme Sterility        # illustrative keyword theme

Public openFDA data only. Themes are a keyword heuristic, not an FDA taxonomy.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .analyze import reason_theme

DEFAULT_ARCHIVE = Path(__file__).resolve().parents[2] / "data" / "recalls_history.csv"


def load_archive(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def find_recall(rows: list[dict], number: str) -> dict | None:
    return next((r for r in rows if r.get("recall_number", "").lower() == number.lower()), None)


def firm_summary(rows: list[dict], name: str) -> dict | None:
    """Recalls whose firm name contains `name` (case-insensitive). Several firm
    spellings can match, so the matched names are listed."""
    hits = [r for r in rows if name.lower() in (r.get("recalling_firm") or "").lower()]
    if not hits:
        return None
    by_class: dict[str, int] = {}
    for r in hits:
        by_class[r.get("classification") or "Unknown"] = by_class.get(r.get("classification") or "Unknown", 0) + 1
    return {"matched_firms": sorted({r["recalling_firm"] for r in hits}), "recalls": len(hits),
            "by_class": dict(sorted(by_class.items())),
            "latest_report_date": max(r.get("report_date") or "" for r in hits),
            "recall_numbers": sorted(r["recall_number"] for r in hits)}


def theme_summary(rows: list[dict], theme: str) -> dict | None:
    hits = [r for r in rows if reason_theme(r.get("reason_for_recall", "")).lower() == theme.lower()]
    if not hits:
        return None
    return {"theme": reason_theme(hits[0].get("reason_for_recall", "")), "recalls": len(hits),
            "class_i": sum(r.get("classification") == "Class I" for r in hits),
            "recall_numbers": sorted(r["recall_number"] for r in hits)[:20]}


def main(argv: list[str] | None = None, archive: Path | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("recall", "firm", "theme"):
        sub.add_parser(name).add_argument("key")
    args = ap.parse_args(argv)
    rows = load_archive(archive or DEFAULT_ARCHIVE)
    handler = {"recall": find_recall, "firm": firm_summary, "theme": theme_summary}[args.cmd]
    result = handler(rows, args.key)
    if result is None:
        print(f"no {args.cmd} found for {args.key!r}")
        return 1
    print(json.dumps(result, indent=2))
    return 0
