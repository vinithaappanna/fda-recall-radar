"""Render a markdown report and a chart from analyzed recall records."""
from __future__ import annotations

import datetime as dt

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .analyze import recalls_by_day

CLASS_ORDER = ["Class I", "Class II", "Class III"]


def render_markdown(summary: dict, spotlight: list[dict],
                    window_start: dt.date, window_end: dt.date,
                    generated_at: dt.datetime | None = None) -> str:
    generated_at = generated_at or dt.datetime.now(dt.timezone.utc)
    lines = [
        "# FDA Recall Radar - daily report",
        "",
        f"Window: {window_start} to {window_end} (by report date). "
        f"Generated {generated_at:%Y-%m-%d %H:%M} UTC.",
        "",
        f"**{summary['total']} recalls** across {summary['days_with_recalls']} active days.",
        "",
        "## By severity",
        "",
        "| Classification | Recalls |",
        "| --- | ---: |",
    ]
    for cls in CLASS_ORDER:
        lines.append(f"| {cls} | {summary['by_classification'].get(cls, 0)} |")
    lines += ["", "## By product area", "", "| Product type | Recalls |", "| --- | ---: |"]
    for ptype, count in sorted(summary["by_product_type"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {ptype} | {count} |")
    lines += ["", "## Top recalling firms", ""]
    for firm, count in summary["top_firms"]:
        lines.append(f"- {firm} ({count})")
    lines += ["", "## Highest-severity recalls in the window", ""]
    for rec in spotlight:
        reason = (rec.get("reason_for_recall") or "no reason given")[:220]
        lines.append(
            f"- **{rec.get('classification', '?')}** ({rec.get('report_date', '?')}): "
            f"{rec.get('recalling_firm', 'Unknown firm')} - {reason}"
        )
    lines += [
        "",
        "![Recalls per day](recalls_last_30d.png)",
        "",
        "Data: [openFDA](https://open.fda.gov/) enforcement reports. Not medical advice.",
        "",
    ]
    return "\n".join(lines)


def plot_daily_counts(records: list[dict], out_path, window_days: int = 30) -> bool:
    by_day = recalls_by_day(records)
    if not by_day:
        return False
    days = [d for d, _ in by_day]
    counts = [c for _, c in by_day]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(days, counts, color="#2b8a3e")
    ax.set_title(f"FDA recalls per day (last {window_days} days)")
    ax.set_ylabel("recalls")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True
