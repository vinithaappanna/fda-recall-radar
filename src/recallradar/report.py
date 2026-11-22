"""Render a markdown report and a chart from analyzed recall records."""
from __future__ import annotations

import datetime as dt

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .analyze import classification_counts, daily_series

CLASS_ORDER = ["Class I", "Class II", "Class III"]


def stale_banner(endpoint_updated: dict | None, today: dt.date, max_days: int = 7) -> str | None:
    """Warning line when any openFDA endpoint has not published for more than
    `max_days` days, so a quiet report is not mistaken for a quiet month.
    Returns None when every endpoint is fresh or nothing is known."""
    if not endpoint_updated:
        return None
    late = {ep: (today - d).days for ep, d in endpoint_updated.items() if (today - d).days > max_days}
    if not late:
        return None
    parts = ", ".join(f"{ep} {n} days" for ep, n in sorted(late.items()))
    return (f"> **Stale upstream data:** openFDA has not published for over {max_days} days "
            f"({parts}). Recent days may be missing here until it does.")


def render_markdown(summary: dict, spotlight: list[dict],
                    window_start: dt.date, window_end: dt.date,
                    data_through: dt.date | None = None,
                    generated_at: dt.datetime | None = None,
                    endpoint_updated: dict[str, dt.date] | None = None,
                    lag: dict | None = None,
                    lag_by_class: dict | None = None,
                    repeaters: list[dict] | None = None,
                    severity_by_product: dict | None = None,
                    statuses: list[tuple] | None = None,
                    unarchived: int = 0,
                    weekly: list[dict] | None = None,
                    themes: list[dict] | None = None,
                    themes_product: dict | None = None,
                    firms_by_product: dict | None = None,
                    open_ages: list[dict] | None = None,
                    class_one_months: list[dict] | None = None,
                    month_themes: dict | None = None,
                    quality_notes: dict | None = None,
                    archive_size: int | None = None,
                    concentration: dict | None = None) -> str:
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
    ]
    banner = stale_banner(endpoint_updated, generated_at.date())
    if banner:
        lines += [banner, ""]
    lines += [
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
    if lag and lag.get("count"):
        lines += [
            "", "## Reporting lag", "",
            f"Days from recall initiation to the enforcement report, over the "
            f"{lag['count']} recalls in the window with both dates: "
            f"median **{lag['median']}**, p90 {lag['p90']}, longest {lag['max']}.",
        ]
    if lag_by_class:
        lines += ["", "| Classification | Recalls | Median lag | p90 |",
                  "| --- | ---: | ---: | ---: |"]
        for cls in CLASS_ORDER:
            if cls in lag_by_class:
                row = lag_by_class[cls]
                lines.append(f"| {cls} | {row['count']} | {row['median']} | {row['p90']} |")
    lines += ["", "## Top recalling firms", ""]
    for firm, count in summary["top_firms"]:
        lines.append(f"- {firm} ({count})")
    if severity_by_product:
        lines += ["", "## Severity by product area", "",
                  "| Product type | Class I | Class II | Class III | Class I share |",
                  "| --- | ---: | ---: | ---: | ---: |"]
        for ptype, c in sorted(severity_by_product.items()):
            total = sum(c.values())
            share = f"{c['Class I'] / total:.0%}" if total else "-"
            lines.append(f"| {ptype} | {c['Class I']} | {c['Class II']} | {c['Class III']} | {share} |")
    if weekly:
        lines += ["", "## Recalls by week", "", "| Week of | Recalls | Class I |",
                  "| --- | ---: | ---: |"]
        for w in weekly:
            lines.append(f"| {w['week_start']} | {w['recalls']} | {w['class_i']} |")
    if themes:
        lines += ["", "## Recall reason themes", "",
                  "Keyword grouping of the free-text reason (illustrative heuristic, not an FDA taxonomy).", "",
                  "![Recalls by reason theme](recall_themes.png)", "",
                  "| Theme | Recalls | Class I |", "| --- | ---: | ---: |"]
        for t in themes:
            lines.append(f"| {t['theme']} | {t['recalls']} | {t['class_i']} |")
    if themes_product:
        lines += ["", "## Top reason theme by product area", "",
                  "| Product area | Recalls | Top theme | Share of area |", "| --- | ---: | --- | ---: |"]
        for ptype in sorted(themes_product):
            counts = themes_product[ptype]
            total = sum(counts.values())
            top, n = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            lines.append(f"| {ptype} | {total} | {top} | {n / total:.0%} |")
    if firms_by_product:
        lines += ["", "## Top recalling firms by product area", "",
                  "| Product area | Firm | Recalls | Class I |", "| --- | --- | ---: | ---: |"]
        for area in sorted(firms_by_product):
            for firm, n, c1 in firms_by_product[area]:
                lines.append(f"| {area} | {firm} | {n} | {c1} |")
    if statuses:
        lines += ["", "## Recall status", "", "| Status | Recalls | Share |", "| --- | ---: | ---: |"]
        for st, n, share in statuses:
            lines.append(f"| {st} | {n} | {share:.0%} |")
    if open_ages:
        lines += ["", "## Age of open recalls", "",
                  "Days since initiation for recalls still marked Ongoing.", "",
                  "| Class | Open | Median age (days) | Oldest (days) | Open > 90 days |",
                  "| --- | ---: | ---: | ---: | ---: |"]
        for o in open_ages:
            lines.append(f"| {o['classification']} | {o['open']} | {o['median_age_days']:g} | {o['oldest_days']} | {o.get('long_open', 0)} |")
    if month_themes and month_themes.get("months"):
        cols = month_themes["themes"]
        lines += ["", "## Reason themes by month", "",
                  "Top reason themes overall (keyword heuristic, not an FDA taxonomy), by report month.", "",
                  "| Month | " + " | ".join(cols) + " |", "| --- | " + " | ".join("---:" for _ in cols) + " |"]
        for m in month_themes["months"]:
            lines.append(f"| {m['month']} | " + " | ".join(str(m['counts'][c]) for c in cols) + " |")
    if class_one_months:
        lines += ["", "## Class I share by month", "",
                  "Share of recalls classed as Class I (most serious) by report month. "
                  "Recent months can be partial because openFDA publishes in batches.", "",
                  "| Month | Recalls | Class I | Share |", "| --- | ---: | ---: | ---: |"]
        for m in class_one_months:
            lines.append(f"| {m['month']} | {m['recalls']} | {m['class_i']} | {m['share']:.0%} |")
    if concentration and concentration.get("recalls"):
        lines += ["", "![Top recalling firms](top_firms.png)"]
        c = concentration
        lines += ["", "## Firm concentration", "",
                  f"{c['firms']} distinct firms have {c['recalls']} recall records in the window. "
                  f"The top {c['top']} firms account for {c['top_share']:.0%} of recalls and "
                  f"{c['top_class_i_share']:.0%} of Class I recalls.", ""]
        lines += [f"- {f}: {n}" for f, n in c["top_firms"]]
    if quality_notes and quality_notes.get("records"):
        q = quality_notes
        lines += ["", "## Source data notes", "",
                  f"Scope: the {q['records']} recalls with a report date in the rolling window "
                  f"{window_start} to {window_end}, not the whole archive"
                  + (f" ({archive_size} recalls keyed by recall_number, which keeps recalls after they leave the window)"
                     if archive_size is not None else "")
                  + (f"; {unarchived} of the window recalls have no recall_number and are not in the archive"
                     if unarchived else "")
                  + f". Of the {q['records']}: {q['missing_initiation']} lack an initiation date, "
                  f"{q['bad_dates']} have an unparseable date, {q['report_before_initiation']} are reported "
                  f"before their initiation date, {q['missing_classification']} lack a classification. "
                  "Lag and age sections skip those records."]
    if unarchived:
        lines += ["", f"_Window total includes {unarchived} recalls with no recall_number; "
                      "they are reported here but cannot be keyed into the archive._"]
    if repeaters:
        lines += ["", "## Repeat recallers", "",
                  "Firms with 3+ recalls in the window (a supplier-risk signal).", "",
                  "| Firm | Recalls | Class I |", "| --- | ---: | ---: |"]
        for r in repeaters:
            lines.append(f"| {r['firm']} | {r['recalls']} | {r['class_i']} |")
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


def plot_theme_counts(themes: list[dict], out_path) -> bool:
    """Stacked horizontal bars per reason theme: Class I vs other classes.
    Themes come from a keyword heuristic (illustrative, not an FDA taxonomy)."""
    if not themes:
        return False
    ordered = sorted(themes, key=lambda t: (t["recalls"], t["theme"]))  # largest at top
    names = [t["theme"] for t in ordered]
    class_i = [t["class_i"] for t in ordered]
    other = [t["recalls"] - t["class_i"] for t in ordered]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(names, class_i, color="#c92a2a", label="Class I")
    ax.barh(names, other, left=class_i, color="#adb5bd", label="Class II/III")
    for i, t in enumerate(ordered):
        ax.annotate(str(t["recalls"]), xy=(t["recalls"], i), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=8)
    ax.set_title("Recalls by reason theme (keyword heuristic, illustrative)", fontsize=11)
    ax.set_xlabel("recalls in window")
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def plot_top_firms(firms: list[tuple[str, int]], out_path, n: int = 10) -> bool:
    """Horizontal bar chart of the firms with the most recall records in the
    window. Long names are truncated so the bars stay readable."""
    if not firms:
        return False
    top = firms[:n]
    labels = [f if len(f) <= 38 else f[:35] + "..." for f, _c in top][::-1]
    counts = [c for _f, c in top][::-1]
    fig, ax = plt.subplots(figsize=(9, max(3.5, 0.4 * len(top) + 1.5)))
    ax.barh(labels, counts, color="#2f9e44")
    for i, c in enumerate(counts):
        ax.text(c, i, f" {c}", va="center", fontsize=8)
    ax.set_xlabel("recall records in window")
    ax.set_title("Top recalling firms (window)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True
