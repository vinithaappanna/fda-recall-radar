"""Tests for report rendering: markdown freshness lines and chart semantics."""
import datetime as dt

import pytest

from recallradar import report

SUMMARY = {
    "total": 3,
    "days_with_recalls": 2,
    "by_classification": {"Class I": 1, "Class II": 2, "Class III": 0},
    "by_product_type": {"drug": 2, "food": 1},
    "top_firms": [("Acme Labs", 2), ("Beta Foods", 1)],
}
SPOTLIGHT = [
    {"recalling_firm": "Acme Labs", "classification": "Class I",
     "reason_for_recall": "undeclared allergen", "report_date": "20261101"},
]
START = dt.date(2026, 10, 17)
END = dt.date(2026, 11, 15)


def test_markdown_lists_per_endpoint_freshness():
    md = report.render_markdown(
        SUMMARY, SPOTLIGHT, START, END,
        data_through=dt.date(2026, 11, 4),
        endpoint_updated={"drug": dt.date(2026, 11, 4),
                          "food": dt.date(2026, 11, 2),
                          "device": dt.date(2026, 11, 4)},
    )
    assert "drug 2026-11-04" in md
    assert "food 2026-11-02" in md
    assert "device 2026-11-04" in md
    # per-endpoint line replaces the single blanket date
    assert "published through 2026-11-04" not in md


def test_markdown_falls_back_to_single_date():
    md = report.render_markdown(SUMMARY, SPOTLIGHT, START, END,
                                data_through=dt.date(2026, 11, 4))
    assert "published through 2026-11-04" in md


def test_markdown_omits_freshness_when_unknown():
    md = report.render_markdown(SUMMARY, SPOTLIGHT, START, END)
    assert "published through" not in md
    assert "last_updated" not in md


def test_plot_shades_unpublished_tail(tmp_path):
    records = [
        {"report_date": "20261101", "classification": "Class II",
         "product_type": "drug", "recalling_firm": "Acme",
         "reason_for_recall": "x", "recall_number": "A-1"},
    ]
    out = tmp_path / "chart.png"
    ok = report.plot_daily_counts(records, out, START, END,
                                  data_through=dt.date(2026, 11, 4))
    assert ok and out.exists() and out.stat().st_size > 0


def test_plot_without_freshness_still_renders(tmp_path):
    records = [
        {"report_date": "20261101", "classification": "Class II",
         "product_type": "drug", "recalling_firm": "Acme",
         "reason_for_recall": "x", "recall_number": "A-1"},
    ]
    out = tmp_path / "chart.png"
    assert report.plot_daily_counts(records, out, START, END) is True
