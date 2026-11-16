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


def test_daily_series_fills_missing_days_with_zero(sample_records):
    series = dict(analyze.daily_series(sample_records, dt.date(2026, 11, 9), dt.date(2026, 11, 14)))
    assert len(series) == 6
    assert series[dt.date(2026, 11, 9)] == 0
    assert series[dt.date(2026, 11, 11)] == 0
    assert series[dt.date(2026, 11, 10)] == 3


def test_daily_series_empty_range():
    assert analyze.daily_series([], dt.date(2026, 11, 10), dt.date(2026, 11, 9)) == []


def test_summarize_empty():
    summary = analyze.summarize([])
    assert summary["total"] == 0
    assert summary["first_day"] is None
    assert summary["days_with_recalls"] == 0


def test_backfill_fills_only_blanks():
    from recallradar.analyze import backfill_fields
    archived = {"recall_number": "D-1", "recall_initiation_date": ""}
    fresh = {"recall_number": "D-1", "recall_initiation_date": "20261001"}
    assert backfill_fields(archived, fresh, ["recall_initiation_date"]) is True
    assert archived["recall_initiation_date"] == "20261001"
    # an existing value is never overwritten
    fresh["recall_initiation_date"] = "20261111"
    assert backfill_fields(archived, fresh, ["recall_initiation_date"]) is False
    assert archived["recall_initiation_date"] == "20261001"


def test_reporting_lag_skips_incomplete_and_inverted_records():
    from recallradar.analyze import reporting_lag_days
    records = [
        {"recall_initiation_date": "20261001", "report_date": "20261011"},  # 10
        {"recall_initiation_date": "", "report_date": "20261011"},          # missing
        {"recall_initiation_date": "20261011"},                             # missing report
        {"recall_initiation_date": "20261020", "report_date": "20261011"},  # inverted
        {"recall_initiation_date": "not-a-date", "report_date": "20261011"},
    ]
    assert reporting_lag_days(records) == [10]


def test_lag_summary_median_p90_max():
    from recallradar.analyze import lag_summary
    assert lag_summary([]) == {"count": 0, "median": None, "p90": None, "max": None}
    records = [{"recall_initiation_date": "20261001",
                "report_date": f"202610{day:02d}"} for day in range(2, 12)]
    out = lag_summary(records)
    assert out["count"] == 10
    assert out["median"] == 5.5  # lags 1..10
    assert out["max"] == 10
    assert 1 <= out["p90"] <= 10
