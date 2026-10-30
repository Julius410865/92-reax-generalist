"""#8 NVD CVE records: the NVD CVE API 2.0 (no key), one-day publication windows sampled every 15 days from 2024-01-01 to
2026-10-26 (plus the days halfway between them from 2026-08-08 on, so that fresh records are not rare), every page stored
unmodified.

    python -I tools/records/fetch_nvd_severity.py [--snapshot 2026-10-27]

Rate limit without a key: 5 requests in a rolling 30 seconds, so the script sleeps PAUSE_S (6.5 s) after every request it
makes. A day with more than PAGE results is paged by startIndex. 403 / 429 / 5xx answers are retried after a longer wait.
Pages already recorded in fetch.json are skipped, so a rerun continues where it stopped. The full days are taken (not the
first n records of a longer window), because the API returns records in publication order and a partial page would only
hold the first hours of a window.
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

DOMAIN = "nvd_severity"
API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
PAGE = 2000                                 # the API's maximum resultsPerPage
FIRST, LAST = dt.date(2024, 1, 1), dt.date(2026, 10, 26)
STRIDE = 15                                 # one sampled day every 15 days
FRESH_EXTRA_FROM = dt.date(2026, 8, 8)      # plus one more day halfway between, in the fresh period
PAUSE_S = 6.5                               # >= 30 s / 5 requests, with margin
RETRY_WAITS = (35, 60, 120, 240)
LICENCE = {"name": "NVD public domain; CVE descriptions: CVE Terms of Use (MITRE)",
           "url": "https://www.cve.org/Legal/TermsOfUse",
           "notice": "CVE descriptions (c) The MITRE Corporation, reproduced under the CVE Terms of Use"}
GB = 1024 ** 3
MIN_FREE, EXPECTED = 40 * GB, int(0.2 * GB)


def days() -> list[dt.date]:
    out = []
    d = FIRST
    while d <= LAST:
        out.append(d)
        d += dt.timedelta(days=STRIDE)
    d = FRESH_EXTRA_FROM
    while d <= LAST:
        out.append(d)
        d += dt.timedelta(days=STRIDE)
    return sorted(set(out))


def url_of(day: dt.date, start: int) -> str:
    return (f"{API}?pubStartDate={day.isoformat()}T00:00:00.000&pubEndDate={day.isoformat()}T23:59:59.999"
            f"&noRejected&resultsPerPage={PAGE}&startIndex={start}")


def recorded(snapshot: str, name: str) -> bool:
    d = R.raw_dir(DOMAIN, snapshot)
    log = os.path.join(d, "fetch.json")
    return os.path.exists(log) and name in json.load(open(log))["files"] and os.path.exists(os.path.join(d, name))


def get(snapshot: str, url: str, name: str) -> str:
    """fetch_file with the NVD pause after every request made, and retries on rate-limit / server errors."""
    if recorded(snapshot, name):
        return R.fetch_file(DOMAIN, snapshot, url, name)
    for attempt, wait in enumerate((0,) + RETRY_WAITS):
        if wait:
            print(f"  waiting {wait} s before retry {attempt} of {name}", flush=True)
            time.sleep(wait)
        try:
            path = R.fetch_file(DOMAIN, snapshot, url, name, timeout=180)
            time.sleep(PAUSE_S)
            return path
        except urllib.error.HTTPError as exc:
            print(f"  HTTP {exc.code} on {name}: {exc.headers.get('message', '')}", flush=True)
            if exc.code not in (403, 429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            print(f"  {type(exc).__name__} on {name}: {exc}", flush=True)
        time.sleep(PAUSE_S)
    raise SystemExit(f"{name}: giving up after {len(RETRY_WAITS)} retries; rerun later to resume")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    free = shutil.disk_usage("/").free
    if free - EXPECTED < MIN_FREE:
        raise SystemExit(f"only {free / GB:.1f} GB free on /: stopping (needs {MIN_FREE / GB:.0f} GB to remain)")
    total = 0
    for day in days():
        start = 0
        while True:
            name = f"cves/{day.isoformat()}.{start:05d}.json"
            page = json.load(open(get(a.snapshot, url_of(day, start), name)))
            n, tot = len(page.get("vulnerabilities", [])), page.get("totalResults", 0)
            total += n
            print(f"{day}: start {start}, {n} of {tot} records", flush=True)
            start += PAGE
            if start >= tot or n == 0:
                break
    path = os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")
    log = json.load(open(path))
    log["licence"] = LICENCE
    log["sampling"] = {"days": [d.isoformat() for d in days()], "stride_days": STRIDE, "page": PAGE,
                       "window": "one UTC day per request (pubStartDate T00:00:00.000 to pubEndDate T23:59:59.999)",
                       "noRejected": True}
    json.dump(log, open(path, "w"), indent=1)
    size = sum(f["bytes"] for f in log["files"].values())
    print(f"{total} records on {len(log['files'])} pages, {size / 1e6:.1f} MB stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
