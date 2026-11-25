"""Pure analysis functions over openFDA enforcement records."""
from __future__ import annotations

import datetime as dt
from collections import Counter

SEVERITY_RANK = {"Class I": 3, "Class II": 2, "Class III": 1}


def parse_report_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y%m%d").date()


def severity_rank(classification: str) -> int:
    """Higher means more severe; unknown classifications rank 0."""
    return SEVERITY_RANK.get(classification, 0)


def dedupe_by_recall_number(records: list[dict]) -> list[dict]:
    """Keep the first record per recall_number; records without one are kept."""
    seen: set[str] = set()
    out: list[dict] = []
    for rec in records:
        key = rec.get("recall_number")
        if key:
            if key in seen:
                continue
            seen.add(key)
        out.append(rec)
    return out


def classification_counts(records: list[dict]) -> Counter:
    return Counter(rec.get("classification", "Unknown") for rec in records)


def product_type_counts(records: list[dict]) -> Counter:
    return Counter(rec.get("product_type", "Unknown") for rec in records)


def top_firms(records: list[dict], n: int = 10) -> list[tuple[str, int]]:
    return Counter(rec.get("recalling_firm", "Unknown") for rec in records).most_common(n)


def recalls_by_day(records: list[dict]) -> list[tuple[dt.date, int]]:
    counts: Counter = Counter()
    for rec in records:
        raw = rec.get("report_date")
        if raw:
            counts[parse_report_date(raw)] += 1
    return sorted(counts.items())


def daily_series(records: list[dict], start: dt.date, end: dt.date) -> list[tuple[dt.date, int]]:
    """Recall counts for every day in [start, end], with explicit zeros.

    Days without recalls are missing from the source data, not zero - fill
    them so charts show the real window instead of only active days.
    """
    counts = dict(recalls_by_day(records))
    series = []
    day = start
    while day <= end:
        series.append((day, counts.get(day, 0)))
        day += dt.timedelta(days=1)
    return series


def most_severe(records: list[dict], n: int = 5) -> list[dict]:
    """Most severe records: Class I first, ties broken by newest report date."""
    def key(rec: dict):
        try:
            d = parse_report_date(rec.get("report_date", "19000101"))
        except ValueError:
            d = dt.date(1900, 1, 1)
        return (severity_rank(rec.get("classification", "")), d)

    return sorted(records, key=key, reverse=True)[:n]


def summarize(records: list[dict]) -> dict:
    by_day = recalls_by_day(records)
    return {
        "total": len(records),
        "by_classification": dict(classification_counts(records)),
        "by_product_type": dict(product_type_counts(records)),
        "top_firms": top_firms(records),
        "days_with_recalls": len(by_day),
        "first_day": by_day[0][0] if by_day else None,
        "last_day": by_day[-1][0] if by_day else None,
    }


def backfill_fields(existing: dict, fresh: dict, fields: list[str]) -> bool:
    """Fill blank fields on an archived record from a fresh fetch.

    Returns True when anything changed. Existing values always win - this
    only enriches records archived before a field was tracked.
    """
    changed = False
    for name in fields:
        if not existing.get(name) and fresh.get(name):
            existing[name] = fresh[name]
            changed = True
    return changed


def reporting_lag_days(records: list[dict]) -> list[int]:
    """Days from recall initiation to the enforcement report, per record.

    Records missing either date, with unparseable dates, or with the report
    dated before the initiation (source-data noise) are skipped.
    """
    lags = []
    for rec in records:
        raw_init, raw_rep = rec.get("recall_initiation_date"), rec.get("report_date")
        if not raw_init or not raw_rep:
            continue
        try:
            lag = (parse_report_date(raw_rep) - parse_report_date(raw_init)).days
        except ValueError:
            continue
        if lag >= 0:
            lags.append(lag)
    return lags


def lag_summary(records: list[dict]) -> dict:
    """Median/p90/max reporting lag over records that have both dates."""
    lags = sorted(reporting_lag_days(records))
    if not lags:
        return {"count": 0, "median": None, "p90": None, "max": None}
    mid = len(lags) // 2
    median = lags[mid] if len(lags) % 2 else (lags[mid - 1] + lags[mid]) / 2
    p90 = lags[min(len(lags) - 1, int(len(lags) * 0.9))]
    return {"count": len(lags), "median": median, "p90": p90, "max": lags[-1]}


def lag_by_classification(records: list[dict]) -> dict[str, dict]:
    """Reporting-lag summary per classification (Class I/II/III/Unknown).

    Shows whether the most severe recalls reach the enforcement report
    faster or slower than the rest.
    """
    groups: dict[str, list[dict]] = {}
    for rec in records:
        groups.setdefault(rec.get("classification") or "Unknown", []).append(rec)
    return {cls: lag_summary(recs) for cls, recs in groups.items()
            if lag_summary(recs)["count"]}


def repeat_recallers(records: list[dict], min_recalls: int = 3, n: int = 5) -> list[dict]:
    """Firms with several recalls in the window, with their Class I count.

    A firm appearing repeatedly, especially with Class I recalls, is a
    supplier-risk signal for pharma, device and food buyers. Ties break on
    Class I count, then name.
    """
    firms: dict[str, dict] = {}
    for rec in records:
        name = rec.get("recalling_firm") or "Unknown"
        f = firms.setdefault(name, {"firm": name, "recalls": 0, "class_i": 0})
        f["recalls"] += 1
        f["class_i"] += rec.get("classification") == "Class I"
    out = [f for f in firms.values() if f["recalls"] >= min_recalls]
    return sorted(out, key=lambda f: (-f["recalls"], -f["class_i"], f["firm"]))[:n]


def severity_by_product(records: list[dict]) -> dict[str, dict[str, int]]:
    """Cross-tab: product type -> {classification: count}, every class present."""
    out: dict[str, dict[str, int]] = {}
    for rec in records:
        row = out.setdefault(rec.get("product_type") or "Unknown",
                             {"Class I": 0, "Class II": 0, "Class III": 0})
        cls = rec.get("classification")
        if cls in row:
            row[cls] += 1
    return out


def status_breakdown(records: list[dict]) -> list[tuple[str, int, float]]:
    """(status, count, share) for recall status (Ongoing, Completed,
    Terminated...), largest first. Shows how much of the window is still open."""
    counts = Counter(rec.get("status") or "Unknown" for rec in records)
    total = sum(counts.values())
    return [(st, n, n / total) for st, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def weekly_counts(records: list[dict]) -> list[dict]:
    """Recalls per ISO week (Monday start) with Class I counts, oldest first.
    Records with a missing or unparseable report_date are skipped."""
    weeks: dict[dt.date, dict] = {}
    for rec in records:
        try:
            day = parse_report_date(rec.get("report_date") or "")
        except ValueError:
            continue
        monday = day - dt.timedelta(days=day.weekday())
        w = weeks.setdefault(monday, {"week_start": monday, "recalls": 0, "class_i": 0})
        w["recalls"] += 1
        w["class_i"] += rec.get("classification") == "Class I"
    return [weeks[k] for k in sorted(weeks)]


REASON_THEMES = [
    ("Contamination / particulate", ("particulate", "contaminat", "foreign", "glass", "metal", "mold", "microbial", "bacteria", "listeria", "salmonella", "e. coli")),
    ("Sterility", ("steril", "endotoxin", "lack of assurance")),
    ("Manufacturing practice (CGMP)", ("cgmp", "good manufacturing", "manufacturing practice", "processing control", "process control", "not processed")),
    ("Labeling / undeclared allergen", ("label", "undeclared", "allergen", "misbrand", "packag")),
    ("Potency / dissolution / stability", ("potency", "dissolution", "stability", "out of specification", "oos", "subpotent", "superpotent", "impurit")),
    ("Software / cybersecurity", ("software", "cybersecurity", "vulnerab", "firmware", "ssd", "calibration")),
    ("Regulatory clearance", ("510(k)", "clearance", "unapproved", "not approved")),
    ("Device defect / performance", ("defective", "defect", "disconnect", "separation", "nonconform", "do not conform", "difficult", "unexpectedly", "performance", "adhesi", "mechanism", "fail", "kits contain", "swell", "valve", "wrong")),
]


def reason_theme(reason: str) -> str:
    """Keyword heuristic mapping free-text recall reasons to a coarse theme.
    First matching theme wins; unmatched reasons are 'Other'. Illustrative
    grouping for triage, not an FDA taxonomy."""
    text = (reason or "").lower()
    for name, words in REASON_THEMES:
        if any(w in text for w in words):
            return name
    return "Other"


def reason_theme_counts(records: list[dict]) -> list[dict]:
    """Per theme: recalls and Class I recalls, largest first (ties by name)."""
    themes: dict[str, dict] = {}
    for rec in records:
        t = themes.setdefault(reason_theme(rec.get("reason_for_recall", "")),
                              {"theme": "", "recalls": 0, "class_i": 0})
        t["recalls"] += 1
        t["class_i"] += rec.get("classification") == "Class I"
    out = [dict(v, theme=k) for k, v in themes.items()]
    return sorted(out, key=lambda r: (-r["recalls"], r["theme"]))


def themes_by_product(records: list[dict]) -> dict[str, dict[str, int]]:
    """{product_type: {theme: recalls}} using the keyword reason themes.
    Illustrative heuristic; records without a product_type group as 'Unknown'."""
    out: dict[str, dict[str, int]] = {}
    for rec in records:
        row = out.setdefault(rec.get("product_type") or "Unknown", {})
        t = reason_theme(rec.get("reason_for_recall", ""))
        row[t] = row.get(t, 0) + 1
    return out


def top_firms_by_product(records: list[dict], n: int = 3) -> dict[str, list[tuple[str, int, int]]]:
    """{product_type: [(firm, recalls, class_i)]}, top `n` firms per product
    area. Ties break on Class I count, then firm name. Useful for supplier-risk
    review of one area (for example device makers) rather than all recalls."""
    areas: dict[str, dict[str, list[int]]] = {}
    for rec in records:
        firm = rec.get("recalling_firm") or "Unknown"
        c = areas.setdefault(rec.get("product_type") or "Unknown", {}).setdefault(firm, [0, 0])
        c[0] += 1
        c[1] += rec.get("classification") == "Class I"
    return {area: [(f, c[0], c[1]) for f, c in sorted(firms.items(),
                                                       key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))[:max(n, 0)]]
            for area, firms in areas.items()}


def open_recall_age(records: list[dict], today: dt.date, long_open_days: int = 90) -> list[dict]:
    """Age in days since initiation of still-open recalls (status Ongoing),
    per classification: count, median, oldest and how many are open longer than
    `long_open_days` (strictly greater). Records missing an
    initiation date, with an unparseable one, or dated after `today` are
    skipped. Classes in Class I, II, III order, then others by name."""
    ages: dict[str, list[int]] = {}
    for rec in records:
        if (rec.get("status") or "").lower() != "ongoing":
            continue
        try:
            age = (today - parse_report_date(rec.get("recall_initiation_date") or "")).days
        except ValueError:
            continue
        if age >= 0:
            ages.setdefault(rec.get("classification") or "Unknown", []).append(age)
    order = {"Class I": 0, "Class II": 1, "Class III": 2}
    out = []
    for cls in sorted(ages, key=lambda c: (order.get(c, 3), c)):
        a = sorted(ages[cls])
        mid = len(a) // 2
        median = a[mid] if len(a) % 2 else (a[mid - 1] + a[mid]) / 2
        out.append({"classification": cls, "open": len(a), "median_age_days": median, "oldest_days": a[-1],
                    "long_open": sum(1 for x in a if x > long_open_days)})
    return out


def class_one_share_by_month(records: list[dict], min_recalls: int = 10) -> list[dict]:
    """Share of recalls that are Class I (the most serious classification) per
    report month, oldest first. Months with fewer than min_recalls records are
    skipped as too small to read a share from. Records with a missing or bad
    report date are skipped."""
    months: dict[str, list[int]] = {}
    for rec in records:
        try:
            d = parse_report_date(rec.get("report_date") or "")
        except ValueError:
            continue
        m = months.setdefault(f"{d:%Y-%m}", [0, 0])
        m[0] += 1
        m[1] += rec.get("classification") == "Class I"
    return [{"month": k, "recalls": n, "class_i": c, "share": c / n}
            for k, (n, c) in sorted(months.items()) if n >= min_recalls]


def themes_by_month(records: list[dict], top: int = 4) -> dict:
    """Recall counts per report month for the `top` most common reason themes
    overall (everything else is folded into 'Other themes'). Returns
    {"themes": [...], "months": [{"month", "counts": {theme: n}}]}, months
    oldest first. Records without a parseable report date are skipped."""
    per: dict[str, dict[str, int]] = {}
    overall: dict[str, int] = {}
    for rec in records:
        try:
            d = parse_report_date(rec.get("report_date") or "")
        except ValueError:
            continue
        t = reason_theme(rec.get("reason_for_recall", ""))
        overall[t] = overall.get(t, 0) + 1
        m = per.setdefault(f"{d:%Y-%m}", {})
        m[t] = m.get(t, 0) + 1
    keep = [t for t, _ in sorted(overall.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]
    months = []
    for month in sorted(per):
        counts = {t: per[month].get(t, 0) for t in keep}
        counts["Other themes"] = sum(n for t, n in per[month].items() if t not in keep)
        months.append({"month": month, "counts": counts})
    return {"themes": keep + (["Other themes"] if keep else []), "months": months}


def data_quality_notes(records: list[dict]) -> dict:
    """Counts of source-data oddities so readers know how much to trust the
    date-based sections: missing or unparseable initiation/report dates,
    reports dated before initiation, and missing classification."""
    out = {"records": len(records), "missing_initiation": 0, "bad_dates": 0,
           "report_before_initiation": 0, "missing_classification": 0}
    for rec in records:
        if not rec.get("classification"):
            out["missing_classification"] += 1
        init, rep = rec.get("recall_initiation_date"), rec.get("report_date")
        if not init:
            out["missing_initiation"] += 1
        try:
            d_init = parse_report_date(init) if init else None
            d_rep = parse_report_date(rep or "")
        except ValueError:
            out["bad_dates"] += 1
            continue
        if d_init and d_rep < d_init:
            out["report_before_initiation"] += 1
    return out


def firm_concentration(records: list[dict], top: int = 5) -> dict:
    """How concentrated recalls are among firms: distinct firms, and the share
    of recalls (and of Class I recalls) from the `top` firms with the most
    recalls. A high share means a few recalling firms drive the window.
    Missing firm names count as 'Unknown'. Ties break on name."""
    counts: dict[str, list[int]] = {}
    for rec in records:
        c = counts.setdefault(rec.get("recalling_firm") or "Unknown", [0, 0])
        c[0] += 1
        c[1] += rec.get("classification") == "Class I"
    total = sum(c[0] for c in counts.values())
    total_i = sum(c[1] for c in counts.values())
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1][0], kv[0]))[:top]
    return {"firms": len(counts), "recalls": total, "top": top,
            "top_share": sum(c[0] for _f, c in ranked) / total if total else 0.0,
            "top_class_i_share": sum(c[1] for _f, c in ranked) / total_i if total_i else 0.0,
            "top_firms": [(f, c[0]) for f, c in ranked]}


def oldest_open_recalls(records: list[dict], today: dt.date, n: int = 5) -> list[dict]:
    """The n oldest still-open (status Ongoing) recalls: firm, class,
    initiation date and age in days. Records missing or with unparseable
    initiation dates, or dated after today, are skipped. A long-open recall is
    worth attention, especially a Class I."""
    out = []
    for rec in records:
        if (rec.get("status") or "").lower() != "ongoing":
            continue
        try:
            started = parse_report_date(rec.get("recall_initiation_date") or "")
        except ValueError:
            continue
        age = (today - started).days
        if age < 0:
            continue
        out.append({"firm": rec.get("recalling_firm") or "Unknown",
                    "classification": rec.get("classification") or "Unknown",
                    "initiation_date": started.isoformat(), "age_days": age,
                    "recall_number": rec.get("recall_number") or "(none)"})
    out.sort(key=lambda r: (-r["age_days"], r["firm"]))
    return out[:n]


def lag_by_product_type(records: list[dict]) -> dict[str, dict]:
    """Reporting-lag summary per product type (Drugs, Devices, Food, ...).
    Shows which product areas take longest to reach the enforcement report.
    Product types with no usable lag are omitted."""
    groups: dict[str, list[dict]] = {}
    for rec in records:
        groups.setdefault(rec.get("product_type") or "Unknown", []).append(rec)
    out = {}
    for ptype, recs in groups.items():
        summ = lag_summary(recs)
        if summ["count"]:
            out[ptype] = summ
    return out


def slowest_reported(records: list[dict], n: int = 5) -> list[dict]:
    """The n recalls with the longest initiation-to-report lag (same date
    rules as reporting_lag_days: missing, unparseable or negative lags are
    skipped). Ties break by firm then recall number."""
    out = []
    for rec in records:
        try:
            lag = (parse_report_date(rec.get("report_date") or "")
                   - parse_report_date(rec.get("recall_initiation_date") or "")).days
        except ValueError:
            continue
        if lag < 0:
            continue
        out.append({"recall_number": rec.get("recall_number") or "(none)",
                    "firm": rec.get("recalling_firm") or "Unknown",
                    "classification": rec.get("classification") or "Unknown",
                    "lag_days": lag})
    out.sort(key=lambda r: (-r["lag_days"], r["firm"], r["recall_number"]))
    return out[:n]


LAG_BUCKETS = [("0-14 days", 0, 14), ("15-30 days", 15, 30), ("31-60 days", 31, 60),
               ("61-90 days", 61, 90), ("over 90 days", 91, None)]


def lag_distribution(records: list[dict]) -> list[dict]:
    """Recalls per initiation-to-report lag bucket with share of recalls that
    have a usable lag (same date rules as reporting_lag_days). Buckets are
    fixed so reports stay comparable; empty buckets are kept at 0."""
    lags = reporting_lag_days(records)
    out = []
    for label, lo, hi in LAG_BUCKETS:
        n = sum(1 for lag in lags if lag >= lo and (hi is None or lag <= hi))
        out.append({"bucket": label, "recalls": n, "share": round(n / len(lags), 4) if lags else 0.0})
    return out


def class_mix_by_firm(records: list[dict], min_recalls: int = 3, n: int = 5) -> list[dict]:
    """Firms with at least min_recalls recalls, ranked by Class I share (ties
    by recall count, then name): recalls, Class I count and share. Small
    counts make shares noisy, hence the floor; informational only."""
    agg: dict[str, dict] = {}
    for rec in records:
        a = agg.setdefault(rec.get("recalling_firm") or "Unknown", {"recalls": 0, "class_i": 0})
        a["recalls"] += 1
        a["class_i"] += rec.get("classification") == "Class I"
    out = [{"firm": f, "recalls": a["recalls"], "class_i": a["class_i"],
            "class_i_share": round(a["class_i"] / a["recalls"], 4)}
           for f, a in agg.items() if a["recalls"] >= min_recalls and a["class_i"]]
    out.sort(key=lambda r: (-r["class_i_share"], -r["recalls"], r["firm"]))
    return out[:n]


def report_date_gaps(records: list[dict], n: int = 3) -> dict:
    """Publication rhythm from distinct report dates: how many distinct dates,
    the longest gaps between consecutive dates (days, with the dates either
    side) and the median gap. openFDA publishes in batches, so long gaps are
    expected; this shows how lumpy the feed is. Unparseable dates skipped."""
    days = set()
    for rec in records:
        try:
            days.add(parse_report_date(rec.get("report_date") or ""))
        except ValueError:
            pass
    days = sorted(days)
    gaps = [{"from": a.isoformat(), "to": b.isoformat(), "days": (b - a).days}
            for a, b in zip(days, days[1:])]
    sizes = sorted(g["days"] for g in gaps)
    median = None
    if sizes:
        mid = len(sizes) // 2
        median = sizes[mid] if len(sizes) % 2 else (sizes[mid - 1] + sizes[mid]) / 2
    longest = sorted(gaps, key=lambda g: (-g["days"], g["from"]))[:n]
    return {"report_dates": len(days), "median_gap_days": median, "longest": longest}


def lag_by_report_month(records: list[dict], min_recalls: int = 10) -> list[dict]:
    """Median reporting lag (days from initiation to enforcement report) per
    report month, oldest first. Months with fewer than min_recalls usable
    lags are skipped. openFDA publishes in batches, so a month's lag mostly
    reflects what was published when; informational only."""
    by_month: dict[str, list[int]] = {}
    for rec in records:
        try:
            rep = parse_report_date(rec.get("report_date") or "")
            lag = (rep - parse_report_date(rec.get("recall_initiation_date") or "")).days
        except ValueError:
            continue
        if lag >= 0:
            by_month.setdefault(rep.strftime("%Y-%m"), []).append(lag)
    out = []
    for month in sorted(by_month):
        lags = sorted(by_month[month])
        if len(lags) < min_recalls:
            continue
        mid = len(lags) // 2
        median = lags[mid] if len(lags) % 2 else (lags[mid - 1] + lags[mid]) / 2
        out.append({"month": month, "recalls": len(lags), "median_lag": median})
    return out


def archive_by_report_month(history: list[dict]) -> list[dict]:
    """Archived recalls per report month (whole archive, not the rolling
    window), with Class I counts and shares, oldest first. The archive only
    holds what this project has fetched since it started, so early months are
    partial: read it as coverage, not a historical series."""
    months: dict[str, dict] = {}
    for rec in history:
        try:
            m = parse_report_date(rec.get("report_date") or "").strftime("%Y-%m")
        except ValueError:
            continue
        a = months.setdefault(m, {"recalls": 0, "class_i": 0})
        a["recalls"] += 1
        a["class_i"] += rec.get("classification") == "Class I"
    return [{"month": m, "recalls": a["recalls"], "class_i": a["class_i"],
             "class_i_share": round(a["class_i"] / a["recalls"], 4)} for m, a in sorted(months.items())]


def status_by_classification(records: list[dict]) -> list[dict]:
    """Per classification: recalls, how many are still Ongoing and the ongoing
    share. Missing classification or status is grouped as "Unknown". Ordered
    Class I, II, III, then others alphabetically."""
    tally: dict[str, list[int]] = {}
    for rec in records:
        cls = rec.get("classification") or "Unknown"
        row = tally.setdefault(cls, [0, 0])
        row[0] += 1
        if (rec.get("status") or "").lower() == "ongoing":
            row[1] += 1
    order = {"Class I": 0, "Class II": 1, "Class III": 2}
    return [{"classification": c, "recalls": n, "ongoing": o, "ongoing_share": round(o / n, 4)}
            for c, (n, o) in sorted(tally.items(), key=lambda kv: (order.get(kv[0], 3), kv[0]))]
