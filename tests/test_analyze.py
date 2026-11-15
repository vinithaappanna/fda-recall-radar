import datetime as dt

from recallradar import analyze


def test_parse_report_date():
    assert analyze.parse_report_date("20261115") == dt.date(2026, 11, 15)


def test_severity_rank_orders_classes():
    assert analyze.severity_rank("Class I") > analyze.severity_rank("Class II")
    assert analyze.severity_rank("Class II") > analyze.severity_rank("Class III")
    assert analyze.severity_rank("Class IV") == 0


def test_dedupe_by_recall_number(sample_records):
    out = analyze.dedupe_by_recall_number(sample_records)
    numbers = [r["recall_number"] for r in out]
    assert numbers.count("D-001-2027") == 1
    assert len(out) == len(sample_records) - 1


def test_classification_counts(sample_records):
    counts = analyze.classification_counts(sample_records)
    assert counts["Class I"] == 3  # includes the duplicate; dedupe is a separate step
    assert counts["Class III"] == 1


def test_product_type_counts(sample_records):
    counts = analyze.product_type_counts(sample_records)
    assert counts["Food"] == 3
    assert counts["Devices"] == 1


def test_top_firms_respects_n(sample_records):
    top = analyze.top_firms(sample_records, n=2)
    assert top[0] == ("Acme Pharma", 3)
    assert len(top) == 2


def test_recalls_by_day_skips_missing_dates(sample_records):
    by_day = dict(analyze.recalls_by_day(sample_records))
    assert by_day[dt.date(2026, 11, 10)] == 3
    assert by_day[dt.date(2026, 11, 12)] == 1
    assert sum(by_day.values()) == len(sample_records) - 1


def test_most_severe_prefers_class_one_then_newest(sample_records):
    spotlight = analyze.most_severe(sample_records, n=2)
    assert all(r["classification"] == "Class I" for r in spotlight)
    assert spotlight[0]["recall_number"] == "F-003-2027"  # Class I, 11/12 beats 11/10


def test_summarize_empty():
    summary = analyze.summarize([])
    assert summary["total"] == 0
    assert summary["first_day"] is None
    assert summary["days_with_recalls"] == 0
