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
