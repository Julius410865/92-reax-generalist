"""#13 Consumer-product recalls: the CPSC Recalls Retrieval Web Services (SaferProducts.gov REST API, no key, US government),
the whole recall list in one unfiltered JSON response (the service has no paging), stored unmodified.

    python tools/records/fetch_cpsc_hazard.py [--snapshot 2026-10-27]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from tools.records import common as R  # noqa: E402

DOMAIN = "cpsc_hazard"
URL = "https://www.saferproducts.gov/RestWebServices/Recall?format=json"
LICENCE = {"name": "US government work (public domain, 17 U.S.C. 105); CPSC: recall notices may be freely copied and "
                   "distributed, please credit CPSC, no implied endorsement; recall photographs not used",
           "url": "https://www.cpsc.gov/About-CPSC/Policies-Statements-and-Directives/Privacy-Policy",
           "api": "https://www.cpsc.gov/Recalls/CPSC-Recalls-Application-Program-Interface-API-Information"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    R.fetch_file(DOMAIN, a.snapshot, URL, "recalls.json", headers={"Accept": "application/json"}, timeout=600)
    log_path = os.path.join(R.raw_dir(DOMAIN, a.snapshot), "fetch.json")
    log = json.load(open(log_path))
    log["licence"] = LICENCE
    json.dump(log, open(log_path, "w"), indent=1)
    for n, f in log["files"].items():
        print(f"  {n}: {f['bytes']} bytes sha256 {f['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
