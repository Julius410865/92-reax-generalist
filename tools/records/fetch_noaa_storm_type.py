"""#14 NOAA Storm Events: the yearly "details" CSV files of the Storm Events Database bulk download (NCEI, US government
work, public domain), stored as the unmodified .csv.gz files, plus the directory listing they were chosen from and the
bulk-format description.

    python tools/records/fetch_noaa_storm_type.py [--snapshot 2026-10-27]

The directory holds one details file per year, named ..._d<year>_c<created yyyymmdd>.csv.gz; NCEI rewrites the current
year's file each month (the created date changes), so the file names are read from the stored listing. No rate limit is
documented for this HTTPS directory: the files are fetched one at a time with a pause between them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "noaa_storm_type"
BASE = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
YEARS = (2024, 2025, 2026)
DOCS = ("README", "Storm-Data-Bulk-csv-Format.pdf")
LICENCE = {"name": "Public domain (US government work, 17 U.S.C. 105; NOAA NCEI Storm Events Database)",
           "url": "https://www.usa.gov/government-works",
           "source_page": "https://www.ncei.noaa.gov/stormevents/"}
PAUSE_S = 2.0


def details_files(listing: str, years=YEARS) -> dict[int, str]:
    """year -> the details file name with the newest created date in the listing (read as text, never executed)."""
    out: dict[int, tuple[str, str]] = {}
    for name, year, created in re.findall(r'href="(StormEvents_details-ftp_v1\.0_d(\d{4})_c(\d{8})\.csv\.gz)"', listing):
        y = int(year)
        if y in years and (y not in out or created > out[y][1]):
            out[y] = (name, created)
    return {y: v[0] for y, v in sorted(out.items())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    listing = open(R.fetch_file(DOMAIN, a.snapshot, BASE, "csvfiles.index.html"), encoding="utf-8", errors="replace").read()
    files = details_files(listing)
    missing = [y for y in YEARS if y not in files]
    if missing:
        raise SystemExit(f"no details file listed for {missing}")
    for name in list(DOCS) + [files[y] for y in YEARS]:
        if name not in json.load(open(os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")))["files"]:
            time.sleep(PAUSE_S)
        R.fetch_file(DOMAIN, a.snapshot, BASE + name, name)
        print(f"{name}")
    path = os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")
    log = json.load(open(path))
    log["licence"] = LICENCE
    log["details_files"] = {str(y): files[y] for y in YEARS}
    json.dump(log, open(path, "w"), indent=1)
    for n, f in log["files"].items():
        print(f"  {n}: {f['bytes']} bytes sha256 {f['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
