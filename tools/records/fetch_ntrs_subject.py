"""#21 NASA technical reports: the NASA Technical Reports Server API (GET https://ntrs.nasa.gov/api/citations/search, no
key), records of the STI submissions index (the NASA-catalogued records that carry subject categories, abstracts and the
copyright determination; the "chorus" index of publisher-hosted manuscripts has none of them). One page of PER_MONTH records
per calendar month of publication from 2000-01 to 2026-07, plus every record published 2026-08-01 to 2026-10-26 (the fresh
period), every page stored unmodified.

    python -I tools/records/fetch_ntrs_subject.py [--snapshot 2026-10-27]

Records before 2000 use older category names (e.g. "Fluid Mechanics And Heat Transfer", "Lunar And Planetary Exploration")
next to the current ones, so they are not fetched. The API allows at most 100 records per page (page.size); the script makes
one request at a time and sleeps PAUSE_S after each. Pages already recorded are skipped, so a rerun resumes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import time
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "ntrs_subject"
API = "https://ntrs.nasa.gov/api/citations/search"
FIRST_MONTH, LAST_MONTH = (2000, 1), (2026, 7)
FRESH_FROM, FRESH_TO = dt.date(2026, 8, 1), dt.date(2026, 10, 26)
PER_MONTH = 45                  # 319 months x 45 + the fresh period stays under ~15,000 records
PAGE_MAX = 100                  # documented maximum page.size
PAUSE_S = 1.0
RETRY_WAITS = (10, 30, 90, 240)
LICENCE = {"name": "US government work, NTRS records marked Public Use Permitted", "url": "https://ntrs.nasa.gov"}
GB = 1024 ** 3
MIN_FREE, EXPECTED = 40 * GB, int(0.3 * GB)


def months() -> list[tuple[dt.date, dt.date]]:
    out, (y, m) = [], FIRST_MONTH
    while (y, m) <= LAST_MONTH:
        nxt = (y + (m == 12), m % 12 + 1)
        out.append((dt.date(y, m, 1), dt.date(*nxt, 1)))
        y, m = nxt
    return out


def url_of(gte: dt.date, lt: dt.date, size: int, start: int) -> str:
    return (f"{API}?index=submissions&published.gte={gte.isoformat()}&published.lt={lt.isoformat()}"
            f"&page.size={size}&page.from={start}")


def get(snapshot: str, url: str, name: str) -> str:
    d = R.raw_dir(DOMAIN, snapshot)
    log = os.path.join(d, "fetch.json")
    if os.path.exists(log) and name in json.load(open(log))["files"] and os.path.exists(os.path.join(d, name)):
        return os.path.join(d, name)
    for attempt, wait in enumerate((0,) + RETRY_WAITS):
        if wait:
            print(f"  waiting {wait} s before retry {attempt} of {name}", flush=True)
            time.sleep(wait)
        try:
            path = R.fetch_file(DOMAIN, snapshot, url, name, headers={"Accept": "application/json"}, timeout=180)
            time.sleep(PAUSE_S)
            return path
        except urllib.error.HTTPError as exc:
            print(f"  HTTP {exc.code} on {name}: {exc.read()[:300]!r}", flush=True)
            if exc.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            print(f"  {type(exc).__name__} on {name}: {exc}", flush=True)
        time.sleep(PAUSE_S)
    raise SystemExit(f"{name}: giving up; rerun later to resume")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    free = shutil.disk_usage("/").free
    if free - EXPECTED < MIN_FREE:
        raise SystemExit(f"only {free / GB:.1f} GB free on /: stopping (needs {MIN_FREE / GB:.0f} GB to remain)")
    total = 0
    for gte, lt in months():
        res = json.load(open(get(a.snapshot, url_of(gte, lt, PER_MONTH, 0), f"pages/{gte:%Y-%m}.json")))
        n = len(res.get("results") or [])
        total += n
        print(f"{gte:%Y-%m}: {n} of {res.get('stats', {}).get('total')}", flush=True)
    start, lt = 0, FRESH_TO + dt.timedelta(days=1)
    while True:
        res = json.load(open(get(a.snapshot, url_of(FRESH_FROM, lt, PAGE_MAX, start), f"pages/fresh.{start:05d}.json")))
        n, tot = len(res.get("results") or []), res.get("stats", {}).get("total", 0)
        total += n
        print(f"fresh from {start}: {n} of {tot}", flush=True)
        start += PAGE_MAX
        if n == 0 or start >= tot:
            break
    path = os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")
    log = json.load(open(path))
    log["licence"] = LICENCE
    log["sampling"] = {"index": "submissions", "per_month": PER_MONTH, "months": [m[0].strftime("%Y-%m") for m in months()],
                       "fresh_window": [FRESH_FROM.isoformat(), FRESH_TO.isoformat()]}
    json.dump(log, open(path, "w"), indent=1)
    size = sum(f["bytes"] for f in log["files"].values())
    print(f"{total} records on {len(log['files'])} pages, {size / 1e6:.1f} MB stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
