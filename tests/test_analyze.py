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


def test_lag_by_classification_groups_and_skips_empty():
    from recallradar.analyze import lag_by_classification
    records = [
        {"classification": "Class I", "recall_initiation_date": "20261001", "report_date": "20261011"},
        {"classification": "Class I", "recall_initiation_date": "20261001", "report_date": "20261021"},
        {"classification": "Class II", "recall_initiation_date": "20261001", "report_date": "20261006"},
        {"classification": "Class III", "recall_initiation_date": "", "report_date": "20261006"},
    ]
    out = lag_by_classification(records)
    assert set(out) == {"Class I", "Class II"}  # Class III has no usable lag
    assert out["Class I"]["median"] == 15.0
    assert out["Class II"]["count"] == 1


def test_report_renders_lag_by_class_table():
    import datetime as dt
    from recallradar import report
    md = report.render_markdown(
        {"total": 1, "days_with_recalls": 1, "by_classification": {}, "by_product_type": {}, "top_firms": []},
        [], dt.date(2026, 10, 1), dt.date(2026, 10, 30),
        lag={"count": 2, "median": 5, "p90": 6, "max": 6},
        lag_by_class={"Class I": {"count": 2, "median": 5, "p90": 6, "max": 6}})
    assert "| Class I | 2 | 5 | 6 |" in md


def test_repeat_recallers_threshold_and_order():
    from recallradar.analyze import repeat_recallers
    recs = ([{"recalling_firm": "A", "classification": "Class I"}] * 2
            + [{"recalling_firm": "A", "classification": "Class II"}]
            + [{"recalling_firm": "B", "classification": "Class II"}] * 3
            + [{"recalling_firm": "C", "classification": "Class I"}] * 2)
    out = repeat_recallers(recs)
    assert [f["firm"] for f in out] == ["A", "B"]  # tie on 3 recalls: more Class I first
    assert out[0] == {"firm": "A", "recalls": 3, "class_i": 2}
    assert repeat_recallers(recs, min_recalls=2)[-1]["firm"] == "C"
    assert repeat_recallers([]) == []


def test_report_renders_repeat_recallers():
    import datetime as dt
    from recallradar import report
    md = report.render_markdown(
        {"total": 1, "days_with_recalls": 1, "by_classification": {}, "by_product_type": {}, "top_firms": []},
        [], dt.date(2026, 10, 1), dt.date(2026, 10, 30),
        repeaters=[{"firm": "Acme", "recalls": 4, "class_i": 1}])
    assert "## Repeat recallers" in md and "| Acme | 4 | 1 |" in md


def test_severity_by_product_crosstab():
    from recallradar.analyze import severity_by_product
    recs = [{"product_type": "Drugs", "classification": "Class I"},
            {"product_type": "Drugs", "classification": "Class II"},
            {"product_type": "Food", "classification": "Class III"},
            {"product_type": "Food", "classification": "Weird"}]
    out = severity_by_product(recs)
    assert out["Drugs"] == {"Class I": 1, "Class II": 1, "Class III": 0}
    assert out["Food"] == {"Class I": 0, "Class II": 0, "Class III": 1}  # unknown class ignored


def test_report_renders_severity_by_product():
    import datetime as dt
    from recallradar import report
    md = report.render_markdown(
        {"total": 1, "days_with_recalls": 1, "by_classification": {}, "by_product_type": {}, "top_firms": []},
        [], dt.date(2026, 10, 1), dt.date(2026, 10, 30),
        severity_by_product={"Drugs": {"Class I": 1, "Class II": 3, "Class III": 0}})
    assert "| Drugs | 1 | 3 | 0 | 25% |" in md


def test_status_breakdown_counts_shares_and_unknown():
    from recallradar.analyze import status_breakdown
    recs = [{"status": "Ongoing"}] * 3 + [{"status": "Terminated"}] + [{}]
    out = status_breakdown(recs)
    assert out[0] == ("Ongoing", 3, 0.6)
    assert {s for s, _, _ in out} == {"Ongoing", "Terminated", "Unknown"}
    assert status_breakdown([]) == []


def test_report_renders_status_table():
    import datetime as dt
    from recallradar import report
    md = report.render_markdown(
        {"total": 1, "days_with_recalls": 1, "by_classification": {}, "by_product_type": {}, "top_firms": []},
        [], dt.date(2026, 10, 1), dt.date(2026, 10, 30),
        statuses=[("Ongoing", 3, 0.75)])
    assert "| Ongoing | 3 | 75% |" in md


def test_report_notes_unarchived_recalls():
    import datetime as dt
    from recallradar import report
    args = ({"total": 5, "days_with_recalls": 1, "by_classification": {}, "by_product_type": {}, "top_firms": []},
            [], dt.date(2026, 10, 1), dt.date(2026, 10, 30))
    assert "2 recalls with no recall_number" in report.render_markdown(*args, unarchived=2)
    assert "no recall_number" not in report.render_markdown(*args)


def test_weekly_counts_groups_by_monday_and_skips_bad_dates():
    import datetime as dt
    from recallradar.analyze import weekly_counts
    recs = [
        {"report_date": "20261102", "classification": "Class I"},   # Monday
        {"report_date": "20261108", "classification": "Class II"},  # Sunday, same week
        {"report_date": "20261109", "classification": "Class I"},   # next Monday
        {"report_date": "", "classification": "Class I"},
        {"report_date": "bad"},
    ]
    out = weekly_counts(recs)
    assert [w["week_start"] for w in out] == [dt.date(2026, 11, 2), dt.date(2026, 11, 9)]
    assert out[0] == {"week_start": dt.date(2026, 11, 2), "recalls": 2, "class_i": 1}
    assert weekly_counts([]) == []


def test_report_renders_weekly_table():
    import datetime as dt
    from recallradar import report
    md = report.render_markdown(
        {"total": 1, "days_with_recalls": 1, "by_classification": {}, "by_product_type": {}, "top_firms": []},
        [], dt.date(2026, 10, 1), dt.date(2026, 10, 30),
        weekly=[{"week_start": dt.date(2026, 11, 2), "recalls": 2, "class_i": 1}])
    assert "| 2026-11-02 | 2 | 1 |" in md


def test_reason_theme_keywords_and_priority():
    from recallradar.analyze import reason_theme
    assert reason_theme("Particulate matter identified in solution") == "Contamination / particulate"
    assert reason_theme("Lack of Assurance of Sterility") == "Sterility"
    assert reason_theme("CGMP Deviations") == "Manufacturing practice (CGMP)"
    assert reason_theme("Undeclared milk allergen") == "Labeling / undeclared allergen"
    assert reason_theme("Failed dissolution specification") == "Potency / dissolution / stability"
    assert reason_theme("Contaminated; also CGMP deviations") == "Contamination / particulate"  # first wins
    assert reason_theme("Lack of Processing Controls") == "Manufacturing practice (CGMP)"
    assert reason_theme("Products lack 510(k) clearance.") == "Regulatory clearance"
    assert reason_theme("Cybersecurity vulnerability in protocol") == "Software / cybersecurity"
    assert reason_theme("main lift may unexpectedly drop") == "Device defect / performance"
    assert reason_theme("something else") == "Other" and reason_theme(None) == "Other"


def test_reason_theme_counts_sorted_with_class_i():
    from recallradar.analyze import reason_theme_counts
    recs = [{"reason_for_recall": "CGMP Deviations", "classification": "Class II"},
            {"reason_for_recall": "CGMP deviations", "classification": "Class I"},
            {"reason_for_recall": "Mold found", "classification": "Class I"}]
    out = reason_theme_counts(recs)
    assert out[0] == {"theme": "Manufacturing practice (CGMP)", "recalls": 2, "class_i": 1}
    assert out[1]["theme"] == "Contamination / particulate" and out[1]["class_i"] == 1


def test_report_renders_theme_table_labeled_heuristic():
    from recallradar import analyze, report
    import datetime as dt
    summary = analyze.summarize([{"report_date": "20261110", "classification": "Class I",
                                  "product_type": "Drugs", "recalling_firm": "X"}])
    md = report.render_markdown(summary, [], dt.date(2026, 11, 1), dt.date(2026, 11, 18),
                                themes=[{"theme": "Sterility", "recalls": 3, "class_i": 1}])
    assert "| Sterility | 3 | 1 |" in md and "not an FDA taxonomy" in md


def test_themes_by_product_groups_and_unknown():
    from recallradar.analyze import themes_by_product
    recs = [{"product_type": "Drugs", "reason_for_recall": "CGMP Deviations"},
            {"product_type": "Drugs", "reason_for_recall": "Lack of Assurance of Sterility"},
            {"product_type": "Devices", "reason_for_recall": "Cybersecurity vulnerability"},
            {"reason_for_recall": "weird"}]
    out = themes_by_product(recs)
    assert out["Drugs"] == {"Manufacturing practice (CGMP)": 1, "Sterility": 1}
    assert out["Devices"] == {"Software / cybersecurity": 1}
    assert out["Unknown"] == {"Other": 1}


def test_theme_product_table_picks_top_with_tie_break_and_share():
    from recallradar import report, analyze
    import datetime as dt
    summary = analyze.summarize([{"report_date": "20261110", "classification": "Class I",
                                  "product_type": "Drugs", "recalling_firm": "X"}])
    md = report.render_markdown(summary, [], dt.date(2026, 11, 1), dt.date(2026, 11, 18),
                                themes_product={"Drugs": {"Sterility": 2, "CGMP": 2, "Other": 1}})
    assert "| Drugs | 5 | CGMP | 40% |" in md  # tie broken alphabetically


def test_top_firms_by_product_ranking_ties_and_limit():
    from recallradar.analyze import top_firms_by_product
    def r(area, firm, cls="Class II"):
        return {"product_type": area, "recalling_firm": firm, "classification": cls}
    recs = ([r("Devices", "Acme")] * 3 + [r("Devices", "Beta", "Class I")] * 2 + [r("Devices", "Aaa")] * 2
            + [r("Devices", "Zed")] + [r("Drugs", "Pharma Co")] + [{"recalling_firm": "", "classification": "Class I"}])
    out = top_firms_by_product(recs, n=3)
    # Beta beats Aaa on Class I at equal recall count; Zed is cut by the limit
    assert out["Devices"] == [("Acme", 3, 0), ("Beta", 2, 2), ("Aaa", 2, 0)]
    assert out["Drugs"] == [("Pharma Co", 1, 0)]
    assert out["Unknown"] == [("Unknown", 1, 1)]
    assert top_firms_by_product(recs, n=0)["Devices"] == [] and top_firms_by_product([]) == {}


def test_firms_by_product_section_renders():
    from recallradar import analyze, report
    import datetime as dt
    summary = analyze.summarize([{"report_date": "20261110", "classification": "Class I",
                                  "product_type": "Drugs", "recalling_firm": "X"}])
    md = report.render_markdown(summary, [], dt.date(2026, 11, 1), dt.date(2026, 11, 18),
                                firms_by_product={"Devices": [("Acme", 3, 1)]})
    assert "| Devices | Acme | 3 | 1 |" in md


def test_open_recall_age_filters_and_orders():
    import datetime as dt
    from recallradar.analyze import open_recall_age
    today = dt.date(2026, 11, 20)
    def r(cls, init, status="Ongoing"):
        return {"classification": cls, "recall_initiation_date": init, "status": status}
    recs = [r("Class II", "20261110"), r("Class II", "20261030"), r("Class I", "20261119"),
            r("Class II", "20261101", "Completed"),      # closed: ignored
            r("Class III", ""), r("Class III", "garbage"), r("Class III", "20261201"),   # missing/bad/future
            r("Weird", "20261120")]
    out = open_recall_age(recs, today)
    assert [o["classification"] for o in out] == ["Class I", "Class II", "Weird"]
    assert out[0] == {"classification": "Class I", "open": 1, "median_age_days": 1, "oldest_days": 1, "long_open": 0}
    assert out[1] == {"classification": "Class II", "open": 2, "median_age_days": 15.5, "oldest_days": 21, "long_open": 0}
    assert out[2]["median_age_days"] == 0           # initiated today: age 0 is valid
    assert open_recall_age([], today) == []


def test_open_ages_section_renders():
    from recallradar import analyze, report
    import datetime as dt
    summary = analyze.summarize([{"report_date": "20261110", "classification": "Class I",
                                  "product_type": "Drugs", "recalling_firm": "X"}])
    md = report.render_markdown(summary, [], dt.date(2026, 11, 1), dt.date(2026, 11, 18),
                                open_ages=[{"classification": "Class II", "open": 2,
                                            "median_age_days": 15.0, "oldest_days": 21}])
    assert "| Class II | 2 | 15 | 21 |" in md


def test_class_one_share_by_month():
    from recallradar.analyze import class_one_share_by_month
    def r(d, cls):
        return {"report_date": d, "classification": cls}
    recs = ([r("20261005", "Class I")] * 3 + [r("20261006", "Class II")] * 7
            + [r("20261101", "Class I")] * 2          # Nov too small
            + [r("", "Class I"), r("bad", "Class I")])
    out = class_one_share_by_month(recs, min_recalls=10)
    assert out == [{"month": "2026-10", "recalls": 10, "class_i": 3, "share": 0.3}]
    assert class_one_share_by_month(recs, min_recalls=2)[1]["month"] == "2026-11"
    assert class_one_share_by_month([]) == []


def test_class_one_months_section_renders():
    from recallradar import analyze, report
    import datetime as dt
    summary = analyze.summarize([{"report_date": "20261110", "classification": "Class I",
                                  "product_type": "Drugs", "recalling_firm": "X"}])
    md = report.render_markdown(summary, [], dt.date(2026, 11, 1), dt.date(2026, 11, 18),
                                class_one_months=[{"month": "2026-10", "recalls": 10, "class_i": 3, "share": 0.3}])
    assert "| 2026-10 | 10 | 3 | 30% |" in md


def test_themes_by_month_top_and_fold():
    from recallradar.analyze import themes_by_month, reason_theme
    contam = "Listeria monocytogenes contamination"
    cgmp = "CGMP Deviations."
    odd = "zzz unusual"
    assert len({reason_theme(contam), reason_theme(cgmp), reason_theme(odd)}) == 3
    def r(d, reason):
        return {"report_date": d, "reason_for_recall": reason}
    recs = [r("20261001", contam)] * 3 + [r("20261101", contam), r("20261102", cgmp),
            r("20261103", odd), r("", cgmp), r("bad", cgmp)]
    out = themes_by_month(recs, top=1)
    assert out["themes"] == [reason_theme(contam), "Other themes"]
    assert [m["month"] for m in out["months"]] == ["2026-10", "2026-11"]
    nov = out["months"][1]["counts"]
    assert nov[reason_theme(contam)] == 1 and nov["Other themes"] == 2
    assert themes_by_month([]) == {"themes": [], "months": []}


def test_month_themes_section_renders():
    from recallradar import analyze, report
    import datetime as dt
    summary = analyze.summarize([{"report_date": "20261110", "classification": "Class I",
                                  "product_type": "Drugs", "recalling_firm": "X"}])
    md = report.render_markdown(summary, [], dt.date(2026, 11, 1), dt.date(2026, 11, 18),
                                month_themes={"themes": ["A", "Other themes"],
                                              "months": [{"month": "2026-10", "counts": {"A": 3, "Other themes": 1}}]})
    assert "| 2026-10 | 3 | 1 |" in md


def test_data_quality_notes_counts_each_oddity():
    from recallradar.analyze import data_quality_notes
    recs = [
        {"classification": "Class I", "recall_initiation_date": "20261001", "report_date": "20261010"},   # clean
        {"classification": "", "recall_initiation_date": "20261001", "report_date": "20261010"},          # no class
        {"classification": "Class II", "recall_initiation_date": "", "report_date": "20261010"},          # no init
        {"classification": "Class II", "recall_initiation_date": "20261020", "report_date": "20261010"},  # before
        {"classification": "Class II", "recall_initiation_date": "garbage", "report_date": "20261010"},   # bad
    ]
    assert data_quality_notes(recs) == {"records": 5, "missing_initiation": 1, "bad_dates": 1,
                                        "report_before_initiation": 1, "missing_classification": 1}
    assert data_quality_notes([])["records"] == 0


def test_source_notes_section_renders_only_with_records():
    from recallradar import analyze, report
    import datetime as dt
    summary = analyze.summarize([{"report_date": "20261110", "classification": "Class I",
                                  "product_type": "Drugs", "recalling_firm": "X"}])
    args = (summary, [], dt.date(2026, 11, 1), dt.date(2026, 11, 18))
    md = report.render_markdown(*args, quality_notes={"records": 9, "missing_initiation": 1, "bad_dates": 0,
                                                       "report_before_initiation": 2, "missing_classification": 0})
    assert "Source data notes" in md and "2 are reported before their initiation date" in md
    assert "Source data notes" not in report.render_markdown(*args, quality_notes={"records": 0})
    scoped = report.render_markdown(*args, unarchived=2, archive_size=462, quality_notes={
        "records": 394, "missing_initiation": 0, "bad_dates": 0,
        "report_before_initiation": 0, "missing_classification": 0})
    assert "the 394 recalls with a report date in the rolling window 2026-11-01 to 2026-11-18" in scoped
    assert "462 recalls keyed by recall_number" in scoped and "2 of the window recalls have no recall_number" in scoped


def test_open_recall_age_counts_long_open_strictly_over_threshold():
    import datetime as dt
    from recallradar.analyze import open_recall_age
    today = dt.date(2026, 11, 20)
    def r(days):
        return {"classification": "Class II", "status": "Ongoing",
                "recall_initiation_date": (today - dt.timedelta(days=days)).strftime("%Y%m%d")}
    out = open_recall_age([r(89), r(90), r(91), r(200)], today)
    assert out[0]["long_open"] == 2                      # 91 and 200; exactly 90 is not over
    assert open_recall_age([r(10), r(20)], today, long_open_days=15)[0]["long_open"] == 1


def test_firm_concentration_shares_and_ties():
    from recallradar.analyze import firm_concentration
    recs = ([{"recalling_firm": "A", "classification": "Class I"}] * 3
            + [{"recalling_firm": "B", "classification": "Class II"}] * 3
            + [{"recalling_firm": "C", "classification": "Class I"}]
            + [{"classification": "Class II"}])                       # no firm name
    out = firm_concentration(recs, top=2)
    assert out["firms"] == 4 and out["recalls"] == 8
    assert out["top_firms"] == [("A", 3), ("B", 3)]                    # tie broken by name
    assert out["top_share"] == 6 / 8 and out["top_class_i_share"] == 3 / 4
    empty = firm_concentration([])
    assert empty["recalls"] == 0 and empty["top_share"] == 0.0 and empty["top_firms"] == []


def test_firm_concentration_section_renders():
    from recallradar import analyze, report
    import datetime as dt
    summary = analyze.summarize([{"report_date": "20261110", "classification": "Class I",
                                  "product_type": "Drugs", "recalling_firm": "X"}])
    conc = {"firms": 4, "recalls": 8, "top": 2, "top_share": 0.75, "top_class_i_share": 0.75,
            "top_firms": [("A", 3), ("B", 3)]}
    md = report.render_markdown(summary, [], dt.date(2026, 11, 1), dt.date(2026, 11, 18), concentration=conc)
    assert "top 2 firms account for 75% of recalls" in md and "- A: 3" in md


def test_plot_top_firms_renders_and_handles_long_names_and_empty(tmp_path):
    from recallradar import report
    firms = [("A Very Long Recalling Firm Name Incorporated LLC", 12), ("Beta Co", 9), ("Gamma", 4)]
    assert report.plot_top_firms(firms, tmp_path / "f.png") is True
    assert (tmp_path / "f.png").stat().st_size > 1000
    assert report.plot_top_firms([], tmp_path / "e.png") is False
    md = report.render_markdown(*_summary_args(), concentration={
        "firms": 4, "recalls": 8, "top": 2, "top_share": 0.75, "top_class_i_share": 0.75,
        "top_firms": [("A", 3), ("B", 3)]})
    assert "top_firms.png" in md


def _summary_args():
    from recallradar import analyze
    import datetime as dt
    summary = analyze.summarize([{"report_date": "20261110", "classification": "Class I",
                                  "product_type": "Drugs", "recalling_firm": "X"}])
    return summary, [], dt.date(2026, 11, 1), dt.date(2026, 11, 18)


def test_oldest_open_recalls_filters_sorts_and_caps():
    import datetime as dt
    from recallradar.analyze import oldest_open_recalls
    today = dt.date(2026, 11, 22)
    def r(firm, init, status="Ongoing", cls="Class II", num="R-1"):
        return {"recalling_firm": firm, "recall_initiation_date": init, "status": status,
                "classification": cls, "recall_number": num}
    recs = [r("New", "20261120"), r("Old", "20260201", cls="Class I", num="R-2"),
            r("Mid", "20260901", num="R-3"), r("Done", "20260101", status="Completed"),
            r("Bad", "garbage"), r("Future", "20270101")]
    out = oldest_open_recalls(recs, today)
    assert [(o["firm"], o["age_days"]) for o in out] == [("Old", 294), ("Mid", 82), ("New", 2)]
    assert out[0]["classification"] == "Class I" and out[0]["initiation_date"] == "2026-02-01"
    assert len(oldest_open_recalls(recs * 3, today, n=2)) == 2
    assert oldest_open_recalls([], today) == []


def test_oldest_open_section_renders():
    from recallradar import analyze, report
    import datetime as dt
    summary = analyze.summarize([{"report_date": "20261110", "classification": "Class I",
                                  "product_type": "Drugs", "recalling_firm": "X"}])
    md = report.render_markdown(summary, [], dt.date(2026, 11, 1), dt.date(2026, 11, 18),
                                oldest_open=[{"recall_number": "R-2", "firm": "Old Co",
                                              "classification": "Class I",
                                              "initiation_date": "2026-02-01", "age_days": 294}])
    assert "| R-2 | Old Co | Class I | 2026-02-01 | 294 |" in md


def test_lag_by_product_type_and_section_renders():
    from recallradar import analyze, report
    import datetime as dt
    def r(ptype, init, rep):
        return {"product_type": ptype, "recall_initiation_date": init, "report_date": rep,
                "classification": "Class II", "recalling_firm": "X"}
    recs = [r("Drugs", "20261101", "20261111"), r("Drugs", "20261101", "20261121"),
            r("Food", "20261101", "20261104"), r("Devices", "20261101", None),
            r("Food", "20261110", "20261105")]       # negative lag skipped
    out = analyze.lag_by_product_type(recs)
    assert out["Drugs"]["median"] == 15 and out["Drugs"]["count"] == 2
    assert out["Food"]["count"] == 1 and "Devices" not in out
    summary = analyze.summarize(recs)
    md = report.render_markdown(summary, [], dt.date(2026, 11, 1), dt.date(2026, 11, 18),
                                lag_by_product=out)
    assert md.index("| Drugs | 2 | 15 | 20 |") < md.index("| Food | 1 | 3 | 3 |")
    assert analyze.lag_by_product_type([]) == {}


def test_slowest_reported_orders_skips_bad_and_renders():
    from recallradar import analyze, report
    import datetime as dt
    def r(num, firm, init, rep):
        return {"recall_number": num, "recalling_firm": firm, "recall_initiation_date": init,
                "report_date": rep, "classification": "Class II", "product_type": "Food"}
    recs = [r("R-1", "B", "20261001", "20261101"), r("R-2", "A", "20261001", "20261101"),
            r("R-3", "C", "20261001", "20261005"), r("R-4", "D", "20261105", "20261101"),
            r("R-5", "E", "bad", "20261101"), r("R-6", "F", None, None)]
    out = analyze.slowest_reported(recs, n=3)
    assert [(o["recall_number"], o["lag_days"]) for o in out] == [("R-2", 31), ("R-1", 31), ("R-3", 4)]
    assert analyze.slowest_reported([]) == []
    md = report.render_markdown(analyze.summarize(recs), [], dt.date(2026, 11, 1), dt.date(2026, 11, 18),
                                slowest=out)
    assert "| R-2 | A | Class II | 31 |" in md


def test_lag_distribution_buckets_edges_and_render():
    from recallradar import analyze, report
    import datetime as dt
    def r(lag):
        init = dt.date(2026, 1, 1)
        return {"recall_initiation_date": init.strftime("%Y%m%d"),
                "report_date": (init + dt.timedelta(days=lag)).strftime("%Y%m%d")}
    recs = [r(0), r(14), r(15), r(30), r(31), r(90), r(91), r(500), {"report_date": "20260101"}]
    out = {b["bucket"]: b["recalls"] for b in analyze.lag_distribution(recs)}
    assert out == {"0-14 days": 2, "15-30 days": 2, "31-60 days": 1, "61-90 days": 1, "over 90 days": 2}
    assert sum(b["share"] for b in analyze.lag_distribution(recs)) > 0.999
    assert all(b["recalls"] == 0 and b["share"] == 0.0 for b in analyze.lag_distribution([]))
    md = report.render_markdown(analyze.summarize(recs), [], dt.date(2026, 11, 1), dt.date(2026, 11, 18),
                                lag_dist=analyze.lag_distribution(recs))
    assert "| 0-14 days | 2 | 25.0% |" in md


def test_class_mix_by_firm_floor_order_and_render():
    from recallradar import analyze, report
    import datetime as dt
    def r(firm, cls): return {"recalling_firm": firm, "classification": cls}
    recs = ([r("A", "Class I")] * 2 + [r("A", "Class II")] + [r("B", "Class I")] * 3
            + [r("C", "Class II")] * 5 + [r("D", "Class I")])        # D below floor, C no Class I
    out = analyze.class_mix_by_firm(recs)
    assert [(o["firm"], o["class_i_share"]) for o in out] == [("B", 1.0), ("A", 0.6667)]
    assert analyze.class_mix_by_firm([]) == []
    md = report.render_markdown(analyze.summarize(recs), [], dt.date(2026, 11, 1), dt.date(2026, 11, 18),
                                firm_class_mix=out)
    assert "| B | 3 | 3 | 100.0% |" in md
