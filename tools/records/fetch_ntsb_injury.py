"""#11 NTSB aviation accidents: the NTSB downloadable aviation dataset (data.ntsb.gov/avdata, US government work, public
domain), stored as the unmodified Microsoft Access zips: avall.zip (2008 to present, rebuilt monthly) and every weekly
update file created after it, plus the directory page they were chosen from and the schema / release notes.

    python tools/records/fetch_ntsb_injury.py [--snapshot 2026-10-27]

The directory page lists file name, creation time and size; the weekly files (up<dd><MON>.zip) are rolling, so the ones to
apply on top of avall.zip are read from the stored page. No rate limit is documented for the download directory: the files
are fetched one at a time with a pause between them. The download is refused above 3 GB or when less than 40 GB of disk
would remain.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "ntsb_injury"
INDEX_URL = "https://data.ntsb.gov/avdata"
FILE_URL = "https://data.ntsb.gov/avdata/FileDirectory/DownloadFile?fileID={}"
DOCS = ("eadmspub.pdf", "MDB_Release_Notes.pdf")
LICENCE = {"name": "Public domain (US government work, 17 U.S.C. 105; NTSB aviation accident database)",
           "url": "https://www.usa.gov/government-works",
           "source_page": "https://data.ntsb.gov/avdata"}
MAX_BYTES = 3 * 10 ** 9
MIN_FREE_AFTER = 40 * 10 ** 9
PAUSE_S = 2.0


def listing(page: str) -> dict[str, tuple[dt.datetime, int]]:
    """file name -> (creation time, size) from the directory page (read as text, never executed)."""
    out = {}
    for name, when, size in re.findall(r'<td id="fileName">\s*([^<\s]+)\s*</td>\s*<td id="fileDate">\s*([^<]+?)\s*</td>'
                                       r'\s*<td id="fileSize">\s*(\d+)\s*</td>', page):
        out[name] = (dt.datetime.strptime(when, "%m/%d/%Y %I:%M:%S %p"), int(size))
    return out


def plan(files: dict[str, tuple[dt.datetime, int]], snapshot: str) -> list[str]:
    """avall.zip, then the weekly updates created after it (oldest first), then the documentation."""
    base_time = files["avall.zip"][0]
    end = dt.datetime.fromisoformat(snapshot) + dt.timedelta(days=1)
    ups = sorted((t, n) for n, (t, _) in files.items() if re.fullmatch(r"up\d{2}[A-Z]{3}\.zip", n) and base_time < t < end)
    return ["avall.zip"] + [n for _, n in ups] + [d for d in DOCS if d in files]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    page = open(R.fetch_file(DOMAIN, a.snapshot, INDEX_URL, "avdata.index.html"), encoding="utf-8", errors="replace").read()
    files = listing(page)
    names = plan(files, a.snapshot)
    total = sum(files[n][1] for n in names)
    free = shutil.disk_usage(R.RAW).free
    if total > MAX_BYTES or free - total < MIN_FREE_AFTER:
        raise SystemExit(f"refusing: {total} bytes to fetch, {free} bytes free")
    path = os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")
    for name in names:
        if name not in json.load(open(path))["files"]:
            time.sleep(PAUSE_S)
        R.fetch_file(DOMAIN, a.snapshot, FILE_URL.format(name), name, timeout=900)
        print(f"{name} (created {files[name][0]:%Y-%m-%d %H:%M}, {files[name][1]} bytes)")
    log = json.load(open(path))
    log["licence"] = LICENCE
    log["apply_order"] = [n for n in names if n.endswith(".zip")]
    log["created"] = {n: files[n][0].isoformat() for n in names}
    json.dump(log, open(path, "w"), indent=1)
    for n, f in log["files"].items():
        print(f"  {n}: {f['bytes']} bytes sha256 {f['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
