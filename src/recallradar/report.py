"""Render a markdown report and a chart from analyzed recall records."""
from __future__ import annotations

import datetime as dt

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .analyze import classification_counts, daily_series

CLASS_ORDER = ["Class I", "Class II", "Class III"]


def render_markdown(summary: dict, spotlight: list[dict],
                    window_start: dt.date, window_end: dt.date,
                    data_through: dt.date | None = None,
                    generated_at: dt.datetime | None = None,
                    endpoint_updated: dict[str, dt.date] | None = None) -> str:
    generated_at = generated_at or dt.datetime.now(dt.timezone.utc)
    if endpoint_updated:
        parts = ", ".join(f"{ep} {d}" for ep, d in sorted(endpoint_updated.items()))
        freshness = f"openFDA last_updated by endpoint: {parts}. "
    elif data_through:
        freshness = f"openFDA data published through {data_through}. "
    else:
        freshness = ""
    lines = [
        "# FDA Recall Radar - daily report",
        "",
        f"Window: {window_start} to {window_end} (by report date). {freshness}"
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
        "![Recalls by severity class](recalls_by_class.png)",
        "",
        "Data: [openFDA](https://open.fda.gov/) enforcement reports. Not medical advice.",
        "",
    ]
    return "\n".join(lines)


def plot_daily_counts(records: list[dict], out_path,
                      window_start: dt.date, window_end: dt.date,
                      data_through: dt.date | None = None) -> bool:
    series = daily_series(records, window_start, window_end)
    if not series:
        return False
    days = [d for d, _ in series]
    counts = [c for _, c in series]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(days, counts, color="#2b8a3e")
    ax.set_title(f"FDA recalls per day, {window_start} to {window_end}")
    ax.set_ylabel("recalls")
    ax.margins(x=0.01)
    if data_through and data_through < window_end:
        ax.axvspan(data_through + dt.timedelta(days=0.5), window_end,
                   color="grey", alpha=0.12)
        midpoint = data_through + (window_end - data_through) / 2
        ax.annotate("not yet published by openFDA",
                    xy=(midpoint, ax.get_ylim()[1] * 0.5),
                    ha="center", fontsize=8, color="grey")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def plot_classification_share(records: list[dict], out_path) -> bool:
    """Horizontal bar chart of recalls by severity class for the window."""
    counts = classification_counts(records)
    total = sum(counts.values())
    if not total:
        return False
    classes = [c for c in CLASS_ORDER if counts.get(c)]
    values = [counts[c] for c in classes]
    colors = {"Class I": "#c92a2a", "Class II": "#e8590c", "Class III": "#868e96"}
    fig, ax = plt.subplots(figsize=(7, 2.8))
    bars = ax.barh(classes, values, color=[colors[c] for c in classes])
    for bar, val in zip(bars, values):
        ax.annotate(f"{val} ({val / total:.0%})",
                    xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2),
                    xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=9)
    ax.set_title("Recalls by FDA severity class")
    ax.set_xlabel("recalls")
    ax.margins(x=0.18)
    ax.invert_yaxis()  # Class I (most severe) on top
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True
