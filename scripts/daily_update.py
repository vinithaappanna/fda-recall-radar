#!/usr/bin/env python3
"""Daily update: pull the last 30 days of FDA enforcement reports, archive new
recalls, and regenerate the report. Safe to re-run: archiving dedupes on
recall_number."""
from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recallradar import analyze, api, report

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
WINDOW_DAYS = 30

FIELDNAMES = ["recall_number", "report_date", "classification", "product_type",
              "recalling_firm", "reason_for_recall", "status", "source_endpoint"]


def load_history(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {row["recall_number"]: row for row in csv.DictReader(fh)}


def main() -> None:
    end = dt.date.today()
    start = end - dt.timedelta(days=WINDOW_DAYS)

    # Freshness is per endpoint: drug, food and device publish on their own
    # schedules, so track each one's last_updated instead of implying one
    # universal date. The chart shades from the freshest common cutoff.
    endpoint_updated: dict[str, dt.date] = {}
    for product in api.ENDPOINTS:
        try:
            meta = api.fetch_meta(product)
            raw_updated = meta.get("last_updated")
            if raw_updated:
                endpoint_updated[product] = dt.datetime.strptime(
                    raw_updated, "%Y-%m-%d").date()
        except api.OpenFDAError as exc:
            print(f"warning: could not read openFDA meta for {product}: {exc}")
    data_through = min(endpoint_updated.values()) if endpoint_updated else None

    records: list[dict] = []
    for product in api.ENDPOINTS:
        for rec in api.fetch_enforcement(product, start, end):
            rec = dict(rec)
            rec["source_endpoint"] = product
            records.append(rec)
    records = analyze.dedupe_by_recall_number(records)
    print(f"fetched {len(records)} unique recalls for {start}..{end}")

    DATA.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)

    history_path = DATA / "recalls_history.csv"
    history = load_history(history_path)
    new = 0
    for rec in records:
        key = rec.get("recall_number")
        if key and key not in history:
            history[key] = {name: rec.get(name, "") for name in FIELDNAMES}
            new += 1
    with history_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(history.values())
    print(f"archived {new} new recalls; history now holds {len(history)}")

    summary = analyze.summarize(records)
    spotlight = analyze.most_severe(records)
    (REPORTS / "daily_report.md").write_text(
        report.render_markdown(summary, spotlight, start, end, data_through,
                               endpoint_updated=endpoint_updated),
        encoding="utf-8",
    )
    if report.plot_daily_counts(records, REPORTS / "recalls_last_30d.png",
                                start, end, data_through):
        print("wrote chart")
    print("wrote reports/daily_report.md")


if __name__ == "__main__":
    main()
