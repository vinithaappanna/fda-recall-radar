import datetime as dt
import json

import pytest

from recallradar import api


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeSession:
    """Hands out a scripted list of responses, one per call."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.pages[len(self.calls) - 1]


def test_fda_date():
    assert api.fda_date(dt.date(2026, 11, 15)) == "20261115"


def test_date_range_query():
    got = api.date_range_query("report_date", dt.date(2026, 11, 1), dt.date(2026, 11, 15))
    assert got == "report_date:[20261101 TO 20261115]"


def test_date_range_query_rejects_reversed_range():
    with pytest.raises(ValueError):
        api.date_range_query("report_date", dt.date(2026, 11, 15), dt.date(2026, 11, 1))


def test_fetch_returns_empty_on_404():
    session = FakeSession([FakeResponse(404)])
    out = api.fetch_enforcement("drug", dt.date(2026, 11, 1), dt.date(2026, 11, 15), session=session)
    assert out == []


def test_fetch_paginates_until_short_page():
    full_page = [{"recall_number": f"R-{i:03d}"} for i in range(api.PAGE_SIZE)]
    last_page = [{"recall_number": "R-LAST"}]
    session = FakeSession([
        FakeResponse(200, {"results": full_page}),
        FakeResponse(200, {"results": last_page}),
    ])
    out = api.fetch_enforcement("food", dt.date(2026, 11, 1), dt.date(2026, 11, 15), session=session)
    assert len(out) == api.PAGE_SIZE + 1
    assert len(session.calls) == 2
    assert session.calls[1][1]["skip"] == api.PAGE_SIZE


def test_fetch_raises_on_server_error():
    session = FakeSession([FakeResponse(500, {"error": "boom"})])
    with pytest.raises(api.OpenFDAError):
        api.fetch_enforcement("device", dt.date(2026, 11, 1), dt.date(2026, 11, 15), session=session)


def test_fetch_rejects_unknown_product_area():
    with pytest.raises(ValueError):
        api.fetch_enforcement("cosmetics", dt.date(2026, 11, 1), dt.date(2026, 11, 15))
