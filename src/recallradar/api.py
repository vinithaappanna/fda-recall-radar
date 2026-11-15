"""Minimal openFDA enforcement-report client.

No API key required. Without a key openFDA allows 240 requests/minute,
far more than this project needs, but we still sleep briefly between pages.
"""
from __future__ import annotations

import datetime as dt
import time

import requests

BASE_URL = "https://api.fda.gov"
ENDPOINTS = ("drug", "food", "device")
PAGE_SIZE = 100
MAX_PAGES = 10


class OpenFDAError(RuntimeError):
    """Raised when openFDA answers with an unexpected error."""


def fda_date(d: dt.date) -> str:
    """openFDA date fields use YYYYMMDD."""
    return d.strftime("%Y%m%d")


def date_range_query(field: str, start: dt.date, end: dt.date) -> str:
    if end < start:
        raise ValueError("end must be on or after start")
    return f"{field}:[{fda_date(start)} TO {fda_date(end)}]"


def fetch_enforcement(product: str, start: dt.date, end: dt.date,
                      session=None, max_pages: int = MAX_PAGES) -> list[dict]:
    """Fetch enforcement reports for one product area over an inclusive date range.

    Returns [] when nothing matches: openFDA answers 404 in that case.
    `session` is injectable so tests can run without the network.
    """
    if product not in ENDPOINTS:
        raise ValueError(f"unknown product area {product!r}; expected one of {ENDPOINTS}")
    http = session or requests.Session()
    query = date_range_query("report_date", start, end)
    results: list[dict] = []
    for page in range(max_pages):
        resp = http.get(
            f"{BASE_URL}/{product}/enforcement.json",
            params={"search": query, "limit": PAGE_SIZE, "skip": page * PAGE_SIZE},
            timeout=30,
        )
        if resp.status_code == 404:
            break
        if resp.status_code != 200:
            raise OpenFDAError(
                f"openFDA returned {resp.status_code} for {product}: {resp.text[:200]}"
            )
        batch = resp.json().get("results", [])
        results.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        time.sleep(0.25)
    return results
