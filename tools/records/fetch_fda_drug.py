"""#7 FDA drug products: the openFDA drugsfda bulk download (Drugs@FDA; public domain, CC0 1.0), stored unmodified: the
openFDA download index (download.json, which pins the export date) and every drug/drugsfda partition it lists.

    python tools/records/fetch_fda_drug.py [--snapshot 2026-10-27]

Two to three requests in total (no API key; openFDA's documented limits without a key are 240 requests per minute and
1,000 per day per IP).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "fda_drug"
INDEX = "https://api.fda.gov/download.json"
ENDPOINT = ("drug", "drugsfda")
LICENCE = {"name": "CC0-1.0 (openFDA: public domain, Creative Commons CC0 1.0 Universal dedication)",
           "url": "https://open.fda.gov/license/", "terms": "https://open.fda.gov/terms/"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    index = json.load(open(R.fetch_file(DOMAIN, a.snapshot, INDEX, "download.json")))
    entry = index["results"][ENDPOINT[0]][ENDPOINT[1]]
    for part in entry["partitions"]:
        url = part["file"]
        if not url.startswith("https://download.open.fda.gov/"):
            raise SystemExit(f"unexpected partition URL {url!r}")
        R.fetch_file(DOMAIN, a.snapshot, url, os.path.basename(url), timeout=600)
    print(f"/{'/'.join(ENDPOINT)}: export {entry.get('export_date')}, {len(entry['partitions'])} partition(s), "
          f"{entry.get('total_records')} records")
    log_path = os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")
    log = json.load(open(log_path))
    log["licence"] = LICENCE
    log["export_date"] = entry.get("export_date")
    json.dump(log, open(log_path, "w"), indent=1)
    for n, f in log["files"].items():
        print(f"  {n}: {f['bytes']} bytes sha256 {f['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
