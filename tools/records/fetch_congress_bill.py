"""#5 US Congress bills: GovInfo bulk data BILLSTATUS (Library of Congress / GPO, US government work, public domain) for two
completed congresses (117th, 118th) and the bill types hr and s, stored as the unmodified bulk zip files plus the bulk
listing of each folder (no key needed for https://www.govinfo.gov/bulkdata/).

    python -I tools/records/fetch_congress_bill.py [--snapshot 2026-10-27]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "congress_bill"
CONGRESSES = (117, 118)                 # completed congresses only: every bill's outcome is final
BILL_TYPES = ("hr", "s")
BULK = "https://www.govinfo.gov/bulkdata"
LICENCE = {"name": "US government work, public domain (17 U.S.C. 105)",
           "url": "https://www.govinfo.gov/about/policies",
           "note": "BILLSTATUS bulk data of the Library of Congress and the US Government Publishing Office"}
PAUSE_S = 2.0                           # one request at a time, a pause between requests
MIN_FREE_GB, EXPECTED_GB = 40, 0.2      # stop if less than 40 GB would remain after the download


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    free_gb = shutil.disk_usage("/").free / 1e9
    if free_gb - EXPECTED_GB < MIN_FREE_GB:
        raise SystemExit(f"only {free_gb:.1f} GB free on /: stopping (needs {MIN_FREE_GB} GB to remain)")
    for congress in CONGRESSES:
        for bt in BILL_TYPES:
            listing = R.fetch_file(DOMAIN, a.snapshot, f"{BULK}/json/BILLSTATUS/{congress}/{bt}",
                                   f"BILLSTATUS-{congress}-{bt}.listing.json", headers={"Accept": "application/json"})
            files = json.load(open(listing))["files"]
            zips = [f for f in files if f.get("name") == f"BILLSTATUS-{congress}-{bt}.zip"]
            if len(zips) != 1:
                raise SystemExit(f"{congress} {bt}: no bulk zip in the listing")
            time.sleep(PAUSE_S)
            R.fetch_file(DOMAIN, a.snapshot, zips[0]["link"], f"BILLSTATUS-{congress}-{bt}.zip", timeout=900)
            time.sleep(PAUSE_S)
            print(f"{congress} {bt}: {sum(f['name'].endswith('.xml') for f in files)} xml files listed")
    path = os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")
    log = json.load(open(path))
    log["licence"] = LICENCE
    json.dump(log, open(path, "w"), indent=1)
    for n, f in log["files"].items():
        print(f"  {n}: {f['bytes']} bytes sha256 {f['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
