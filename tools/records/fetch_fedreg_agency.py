"""#20 Federal Register documents: the federalregister.gov API v1 (no key; US government work, public domain), documents
published 2025-01-01 to 2026-10-26, fetched in weekly windows (one page of up to 1,000 documents each, following the API's
next_page_url when a week has more), plus the agency list. Responses are stored unmodified.

    python -I tools/records/fetch_fedreg_agency.py [--snapshot 2026-10-27]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "fedreg_agency"
API = "https://www.federalregister.gov/api/v1"
FIRST, LAST = dt.date(2025, 1, 1), dt.date(2026, 10, 26)
FIELDS = ("abstract", "action", "agencies", "document_number", "publication_date", "title", "type")
PER_PAGE = 1000
LICENCE = {"name": "US government work, public domain (17 U.S.C. 105)", "url": "https://www.govinfo.gov/about/policies",
           "note": "Federal Register documents (Office of the Federal Register / GPO) via the federalregister.gov API v1, "
                   "https://www.federalregister.gov/developers/documentation/api/v1 (no key)"}
PAUSE_S = 1.5                           # one request at a time, a pause between requests
MIN_FREE_GB, EXPECTED_GB = 40, 0.3      # stop if less than 40 GB would remain after the download


def window_url(first: dt.date, last: dt.date) -> str:
    q = [("per_page", PER_PAGE), ("order", "oldest"),
         ("conditions[publication_date][gte]", first.isoformat()), ("conditions[publication_date][lte]", last.isoformat())]
    q += [("fields[]", f) for f in FIELDS]
    return f"{API}/documents.json?{urllib.parse.urlencode(q)}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    free_gb = shutil.disk_usage("/").free / 1e9
    if free_gb - EXPECTED_GB < MIN_FREE_GB:
        raise SystemExit(f"only {free_gb:.1f} GB free on /: stopping (needs {MIN_FREE_GB} GB to remain)")
    R.fetch_file(DOMAIN, a.snapshot, f"{API}/agencies.json", "agencies.json")
    time.sleep(PAUSE_S)
    first, total = FIRST, 0
    while first <= LAST:
        last = min(first + dt.timedelta(days=6), LAST)
        url, page, got, count = window_url(first, last), 1, 0, None
        while url:
            path = R.fetch_file(DOMAIN, a.snapshot, url, f"documents/{first}_{last}.p{page}.json")
            body = json.load(open(path))
            got += len(body.get("results") or [])
            count = body.get("count", 0) if count is None else count
            nxt = body.get("next_page_url")
            if nxt and not nxt.startswith(API + "/"):
                raise SystemExit(f"unexpected next_page_url {nxt}")
            url, page = nxt, page + 1
            time.sleep(PAUSE_S)
        if got != count:
            raise SystemExit(f"{first}..{last}: {got} documents read, the API counts {count}")
        total += got
        print(f"{first}..{last}: {got} documents")
        first = last + dt.timedelta(days=1)
    path = os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")
    log = json.load(open(path))
    log["licence"] = LICENCE
    json.dump(log, open(path, "w"), indent=1)
    print(f"{total} documents in {len(log['files']) - 1} pages, "
          f"{sum(f['bytes'] for f in log['files'].values()) / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
