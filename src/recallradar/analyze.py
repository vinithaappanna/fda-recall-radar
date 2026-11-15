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
