import csv
import json

from recallradar import cli

FIELDS = ["recall_number", "report_date", "classification", "recalling_firm", "reason_for_recall"]
ROWS = [
    ["D-1", "20261101", "Class I", "Par Health USA, LLC", "Particulate matter in solution"],
    ["D-2", "20261105", "Class II", "PAR HEALTH USA LLC", "CGMP Deviations"],
    ["F-3", "20261103", "Class II", "Acme Foods", "Undeclared milk allergen"],
    ["D-4", "20261110", "Class I", "Other Co", "Lack of Assurance of Sterility"],
]


def archive(tmp_path):
    p = tmp_path / "h.csv"
    with p.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        w.writerows(ROWS)
    return p


def test_find_recall_case_insensitive_and_missing(tmp_path):
    rows = cli.load_archive(archive(tmp_path))
    assert cli.find_recall(rows, "d-2")["recalling_firm"] == "PAR HEALTH USA LLC"
    assert cli.find_recall(rows, "X-9") is None


def test_firm_summary_merges_spellings(tmp_path):
    out = cli.firm_summary(cli.load_archive(archive(tmp_path)), "par health")
    assert out["recalls"] == 2 and out["by_class"] == {"Class I": 1, "Class II": 1}
    assert len(out["matched_firms"]) == 2 and out["latest_report_date"] == "20261105"
    assert cli.firm_summary(cli.load_archive(archive(tmp_path)), "nobody") is None


def test_theme_summary_and_missing_archive(tmp_path):
    rows = cli.load_archive(archive(tmp_path))
    out = cli.theme_summary(rows, "sterility")
    assert out == {"theme": "Sterility", "recalls": 1, "class_i": 1, "recall_numbers": ["D-4"]}
    assert cli.load_archive(tmp_path / "missing.csv") == []


def test_main_exit_codes_and_json(tmp_path, capsys):
    p = archive(tmp_path)
    assert cli.main(["recall", "D-1"], archive=p) == 0
    assert json.loads(capsys.readouterr().out)["classification"] == "Class I"
    assert cli.main(["firm", "zzz"], archive=p) == 1
    assert "no firm found" in capsys.readouterr().out
